"""Chronological station calibration from archived NWS MOS and original CLI."""
import json,re,math,hashlib,zipfile
from pathlib import Path
from datetime import datetime,timedelta,timezone
from collections import defaultdict,Counter
import numpy as np
from scipy.special import ndtr
from .us_weather import STATIONS,window,parse_cli
from .weather_probability import partition

def utc(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    # IEM MOS JSON encodes naive timestamps documented as UTC.
    if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
    return d.timestamp()

def feature(rows,station,model,date):
    start,end=window(dict(date=date,standard_utc_offset=STATIONS[station]['offset']))
    runtime=(datetime.fromisoformat(date)-timedelta(days=1)).replace(hour=12,tzinfo=timezone.utc).timestamp()
    points={}
    for row in rows:
        if row['station']!=station or row['model']!=model:raise ValueError('MOS model/station mismatch')
        if utc(row['runtime'])!=runtime:continue
        t=utc(row['ftime']);value=row.get('tmp')
        if value is None:continue
        if type(value) not in (int,float) or not math.isfinite(value) or not -100<=value<=150:raise ValueError('Invalid MOS Fahrenheit temperature')
        if t in points and points[t]!=value:raise ValueError('Conflicting MOS valid time')
        points[t]=float(value)
    times=sorted(points);inside=[t for t in times if start-10800<=t<=end+10800]
    if len(inside)<8 or min(inside)>start or max(inside)<end-3600 or any(b-a>10800 for a,b in zip(inside,inside[1:])):raise ValueError('MOS does not cover climate day without long interpolation gaps')
    hours=list(range(int(start),int(end),3600));values=np.interp(hours,inside,[points[t] for t in inside])
    return dict(station=station,date=date,model=model,runtime=runtime,assumed_available_at=runtime+21600,availability_verified=False,day_start=start,day_end=end,sampled_high_f=float(max(values)),sampled_low_f=float(min(values)),hours=len(hours),note='Hourly interpolation of 3-hour MOS temperatures is a forecast feature, not a continuous station extreme. Publication time is conservatively assumed, not verified.')

def cli_archive(path,station,received_at):
    observations={};errors=[]
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist())>250 or sum(i.file_size for i in archive.infolist())>5_000_000:raise ValueError('CLI archive exceeds bounded product budget')
        for info in archive.infolist():
            match=re.fullmatch('CLI'+STATIONS[station]['cli']+r'_(\d{12})\.txt',info.filename)
            if not match or info.file_size>50000:raise ValueError('Unexpected CLI archive member')
            issued=datetime.strptime(match[1],'%Y%m%d%H%M').replace(tzinfo=timezone.utc)
            text=archive.read(info).decode('utf-8',errors='strict')
            document=dict(id=info.filename,productCode='CLI',issuanceTime=issued.isoformat(),productText=text)
            try:
                r=parse_cli(document,station,received_at)
                if not r['complete_day']:continue
                old=observations.get(r['date'])
                if old is None or r['issued_at']<old['issued_at']:observations[r['date']]=r
            except ValueError as exc:errors.append(dict(file=info.filename,error=str(exc)))
    return observations,errors

def fit(rows,station,asof):
    if len(rows)<20 or len({r['date'] for r in rows})!=len(rows):raise ValueError('At least 20 distinct training days required')
    errors=[]
    for row in rows:
        if row['station']!=station or not row['forecast_assumed_available_at']<row['day_start']<row['day_end']<=row['observation_issued_at']<asof:raise ValueError('Station calibration lookahead/identity mismatch')
        errors.append(row['observed_high_f']-row['blend_high_f'])
    bias=float(np.mean(errors));sigma=max(1.,float(np.std(errors,ddof=1)))
    return dict(station=station,bias_f=bias,residual_std_f=sigma,training_days=len(rows),asof=asof,last_training_date=max(r['date'] for r in rows),training_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),availability_verified=False)

def predict(model,gfs,nam,bands,asof):
    bands=partition(bands)
    if model['station']!=gfs['station'] or gfs['station']!=nam['station'] or gfs['date']!=nam['date']:raise ValueError('Prediction source mismatch')
    if max(model['asof'],gfs['assumed_available_at'],nam['assumed_available_at'])>asof:raise ValueError('Prediction lookahead')
    mean=(gfs['sampled_high_f']+nam['sampled_high_f'])/2+model['bias_f'];sigma=model['residual_std_f'];results=[]
    for b in bands:
        if b['unit']!='F':raise ValueError('MOS prediction requires Fahrenheit bands')
        left=0 if b['lower'] is None else ndtr((b['lower']-.5-mean)/sigma)
        right=1 if b['upper'] is None else ndtr((b['upper']+.5-mean)/sigma)
        results.append(dict(**b,probability=float(max(0,right-left))))
    if abs(sum(r['probability'] for r in results)-1)>1e-9:raise ValueError('MOS probability mass lost')
    return dict(station=model['station'],date=gfs['date'],mean_f=mean,std_f=sigma,probabilities=results,calibration_days=model['training_days'],execution_eligible=False,note='Station-calibrated deterministic MOS approximation. Normal residuals and nearest-degree thresholds are model assumptions; historical publication availability remains unverified.')

def prepare(directory):
    directory=Path(directory);registration=json.loads((directory/'registration.json').read_text());collection=json.loads((directory/'collection.json').read_text());receipts={r['file']:r for r in collection['receipts']}
    rows=[];errors=[];models={};metrics={}
    for station in registration['stations']:
        required=[station+'-cli.zip',station+'-GFS.json',station+'-NAM.json']
        if any(n not in receipts for n in required):errors.append(dict(station=station,error='Missing source archive'));continue
        for name in required:
            if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=receipts[name]['sha256']:raise ValueError('Calibration source hash mismatch')
        obs,rejected=cli_archive(directory/required[0],station,receipts[required[0]]['received_at']);errors.extend(rejected)
        raw={m:json.loads((directory/(station+'-'+m+'.json')).read_text()) for m in ['GFS','NAM']}
        # Index cycles once; only the explicitly registered previous-day 12Z run.
        indexed={m:defaultdict(list) for m in raw}
        for m,records in raw.items():
            for r in records:indexed[m][utc(r['runtime'])].append(r)
        date=datetime.fromisoformat(registration['training_dates'][0]);last=datetime.fromisoformat(registration['test_dates'][1]);station_rows=[]
        while date<=last:
            day=date.date().isoformat();date+=timedelta(days=1)
            try:
                if day not in obs:raise ValueError('No complete CLI report')
                runtime=(datetime.fromisoformat(day)-timedelta(days=1)).replace(hour=12,tzinfo=timezone.utc).timestamp()
                pair={m:feature(indexed[m].get(runtime,[]),station,m,day) for m in raw};g,n=pair['GFS'],pair['NAM']
                role='training' if day<=registration['training_dates'][1] else 'validation' if day<=registration['validation_dates'][1] else 'test'
                row=dict(station=station,date=day,role=role,gfs=g,nam=n,gfs_high_f=g['sampled_high_f'],nam_high_f=n['sampled_high_f'],blend_high_f=(g['sampled_high_f']+n['sampled_high_f'])/2,observed_high_f=obs[day]['max_f'],observation_issued_at=obs[day]['issued_at'],observation_product=obs[day]['product_id'],forecast_assumed_available_at=max(g['assumed_available_at'],n['assumed_available_at']),day_start=g['day_start'],day_end=g['day_end'])
                station_rows.append(row)
            except ValueError as exc:errors.append(dict(station=station,date=day,error=str(exc)))
        train=[r for r in station_rows if r['role']=='training'];asof=utc(registration['validation_dates'][0]+'T20:00:00Z')
        # August 27 predictions would already exist by this publication time;
        # reserve the first validation date if its decision is earlier than asof.
        asof=max((r['observation_issued_at'] for r in train),default=0)+1
        try:model=fit(train,station,asof)
        except ValueError as exc:errors.append(dict(station=station,error=str(exc)));continue
        models[station]=model
        for role in ['training','validation','test']:
            subset=[r for r in station_rows if r['role']==role and (role=='training' or r['day_start']-21600>=asof)]
            metrics[station+'/'+role]={}
            for label,key,bias in [('gfs','gfs_high_f',0),('blend','blend_high_f',0),('calibrated','blend_high_f',model['bias_f'])]:
                residuals=[r[key]+bias-r['observed_high_f'] for r in subset]
                metrics[station+'/'+role][label]=dict(days=len(residuals),mae_f=float(np.mean(np.abs(residuals))) if residuals else None,rmse_f=float(np.sqrt(np.mean(np.square(residuals)))) if residuals else None)
        rows.extend(station_rows)
    report=dict(created_at=__import__('time').time(),directory=str(directory),models=models,rows=rows,metrics=metrics,errors=errors,conclusion='Forecast calibration and untouched-date prediction diagnostics, not trading profit. Historical MOS publication availability is assumed, and labels use earliest archived complete CLI rather than exchange payouts.',live_execution=False,code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output=directory/('calibration-'+str(__import__('time').time_ns()));output.mkdir();(output/'report.json').write_text(json.dumps(report,indent=2));return output,report
