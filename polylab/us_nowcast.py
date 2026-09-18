"""Station observations as calibrated predictors, never hard settlement bounds."""
import csv,io,re,math,hashlib,json
from datetime import datetime,timezone
import numpy as np
from scipy.special import ndtr
from .us_mos import utc
from .us_weather import window,STATIONS

def observations(text,station,delay=1800):
    result={};rejected=[]
    rows=csv.DictReader(io.StringIO('\n'.join(line for line in text.splitlines() if not line.startswith('#'))))
    for row in rows:
        if row['station'] not in [station,station[1:]]:raise ValueError('Archive station mismatch')
        try:
            t=utc(row['valid']);raw=row.get('metar','');tokens=raw.split()
            if tokens and tokens[0] in ['METAR','SPECI']:tokens=tokens[1:]
            if not tokens or tokens[0]!=station:raise ValueError('Raw report station mismatch')
            group=re.search(r'\bT([01])(\d{3})[01]\d{3}\b',raw)
            if not group:raise ValueError('No precise T-group; omit rounded whole-C temperature')
            c=int(group[2])/10*(-1 if group[1]=='1' else 1);f=c*1.8+32
            if not -100<=f<=150:raise ValueError('Temperature out of range')
            if t in result and result[t]['temperature_f']!=f:raise ValueError('Conflicting same-time readings')
            result[t]=dict(observed_at=t,assumed_available_at=t+delay,temperature_f=f,source_sha256=hashlib.sha256(raw.encode()).hexdigest())
        except ValueError as exc:rejected.append(dict(valid=row.get('valid'),reason=str(exc)))
    # Remove both sides of conflicting timestamps; no correction ordering is inferred.
    for r in rejected:
        if r['reason']=='Conflicting same-time readings':result.pop(utc(r['valid']),None)
    return sorted(result.values(),key=lambda o:o['observed_at']),rejected

def row_feature(row,obs,mos,cfg):
    start,end=window(dict(date=row['date'],standard_utc_offset=STATIONS[row['station']]['offset']));target=start+cfg['decision_hour_local_standard']*3600
    available=[o for o in obs if start<=o['observed_at']<end and o['assumed_available_at']<=target]
    if len(available)<cfg['minimum_observations']:raise ValueError('Too few observed temperatures')
    latest=max(available,key=lambda o:o['observed_at'])
    if target-latest['observed_at']>cfg['maximum_latest_observation_age_seconds']:raise ValueError('Latest observation too old')
    predictions=[]
    for model in ['GFS','NAM']:
        run=row[model.lower()]['runtime'];points={}
        for p in mos[model]:
            if p['station']!=row['station'] or p['model']!=model:raise ValueError('MOS source identity')
            if utc(p['runtime'])!=run or p.get('tmp') is None:continue
            value=float(p['tmp']);t=utc(p['ftime'])
            if not math.isfinite(value) or not -100<=value<=150:raise ValueError('MOS temperature range')
            if t in points and points[t]!=value:raise ValueError('Conflicting MOS temperature')
            points[t]=value
        times=sorted(points)
        if not times or not times[0]<=latest['observed_at']<=times[-1]:raise ValueError('MOS does not bracket observation')
        index=np.searchsorted(times,latest['observed_at']);left=times[max(0,index-1)];right=times[min(len(times)-1,index)]
        if right-left>10800:raise ValueError('MOS interpolation gap')
        predictions.append(float(np.interp(latest['observed_at'],times,[points[t] for t in times])))
    if row['forecast_assumed_available_at']>=target:raise ValueError('Forecast unavailable')
    observed_max=max(o['temperature_f'] for o in available);error=latest['temperature_f']-sum(predictions)/2
    return dict(station=row['station'],date=row['date'],target=target,blend_high_f=row['blend_high_f'],observed_max_f=observed_max,latest_temperature_f=latest['temperature_f'],latest_observed_at=latest['observed_at'],latest_assumed_available_at=latest['assumed_available_at'],observation_count=len(available),features=[1.,error,observed_max-row['blend_high_f']],observed_high_f=row['observed_high_f'],label_available_at=row['observation_issued_at'],availability_verified=False)

def fit(rows,asof,penalty=10,minimum=20):
    if len(rows)<minimum or len({r['date'] for r in rows})!=len(rows) or len({r['station'] for r in rows})!=1:raise ValueError('Insufficient distinct station training dates')
    if any(not r['latest_assumed_available_at']<=r['target']<r['label_available_at']<asof for r in rows):raise ValueError('Training chronology')
    x=np.array([r['features'] for r in rows],dtype=float);y=np.array([r['observed_high_f']-r['blend_high_f'] for r in rows]);reg=np.diag([0,penalty,penalty])
    if x.shape!=(len(rows),3) or not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('Invalid model inputs')
    coef=np.linalg.solve(x.T@x+reg,x.T@y);errors=[]
    for i in range(len(rows)):
        xx=np.delete(x,i,axis=0);yy=np.delete(y,i);w=np.linalg.solve(xx.T@xx+reg,xx.T@yy);errors.append(float(y[i]-x[i]@w))
    return dict(station=rows[0]['station'],asof=asof,coefficients=coef.tolist(),std_f=max(1.,float(np.sqrt(np.mean(np.square(errors))))),training_days=len(rows),ridge_penalty=penalty,loo_residuals=errors,training_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),availability_verified=False)

def prediction(model,row,rules):
    if row['station']!=model['station'] or model['asof']>=row['target'] or row['latest_assumed_available_at']>row['target']:raise ValueError('Prediction chronology or station mismatch')
    from .us_multiband import event_payoffs
    event_payoffs([],rules)
    if any(r['station']!=row['station'] or r['date']!=row['date'] for r in rules):raise ValueError('Contract identity')
    mean=row['blend_high_f']+float(np.array(row['features'])@model['coefficients']);sigma=model['std_f'];probs=[]
    for r in rules:
        lo=0 if r['lower'] is None else ndtr((r['lower']-.5-mean)/sigma)
        hi=1 if r['upper'] is None else ndtr((r['upper']+.5-mean)/sigma);probs.append(float(max(0,hi-lo)))
    if abs(sum(probs)-1)>1e-9:raise ValueError('Probability mass')
    return dict(mean_f=mean,std_f=sigma,probabilities=probs,model_asof=model['asof'],assumed_observation_cutoff=row['target'],availability_verified=False,execution_eligible=False)
