"""Freeze station forecast inputs for the improved Benter comparison."""
import json,sys,time,hashlib
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_nowcast import observations,row_feature,fit,prediction
from polylab.us_mos import fit as fit_mos

def main():
    source=Path(sys.argv[1]).resolve();history=Path(sys.argv[2]).resolve();cfg=json.loads((source/'registration.json').read_text());study=json.loads((history/'registration.json').read_text())
    rows=json.loads((ROOT/cfg['forecast_rows']).read_text())['rows'];receipts=json.loads((source/'collection.json').read_text())['receipts']
    if (source/'collection-supplement.json').exists():receipts+=json.loads((source/'collection-supplement.json').read_text())['receipts']
    receiptmap={r['file']:r for r in receipts};dest=source/('benter-inputs-'+str(time.time_ns()));dest.mkdir();source_hashes={};result=dict(models={},baseline_models={},features=[],predictions=[],metrics={},errors=[],rejected_observations={})
    for name in ['polylab/us_nowcast.py','tools/prepare_benter_nowcast.py','polylab/us_mos.py']:
        source_hashes[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    (dest/'protocol.json').write_text(json.dumps(dict(created_at=time.time(),forecast_training=study['forecast_training'],model='Registered lambda-10 station observation residual model versus MOS station bias baseline',code_hashes=source_hashes),indent=2),encoding='utf-8')
    for station in cfg['stations']:
        filename=station+'.csv'
        if filename not in receiptmap:result['errors'].append(dict(station=station,error='Missing observation archive'));continue
        path=source/filename;sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if sha!=receiptmap[filename]['sha256']:raise ValueError('Observation source hash')
        source_hashes[str(path)]=sha;obs,rejected=observations(path.read_text(encoding='utf-8'),station,cfg['observation_delay_seconds']);result['rejected_observations'][station]=rejected
        mos={m:json.loads((ROOT/cfg['forecast_source']/(station+'-'+m+'.json')).read_text()) for m in ['GFS','NAM']}
        for m in mos:
            p=ROOT/cfg['forecast_source']/(station+'-'+m+'.json');source_hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        features=[]
        for r in rows:
            if r['station']!=station:continue
            try:features.append(row_feature(r,obs,mos,cfg))
            except ValueError as exc:result['errors'].append(dict(station=station,date=r['date'],error=str(exc)))
        train=[r for r in features if study['forecast_training'][0]<=r['date']<=study['forecast_training'][1]]
        asof=max((r['label_available_at'] for r in train),default=0)+1
        try:
            model=fit(train,asof,cfg['ridge_penalty'],cfg['minimum_training_days']);baseline=fit_mos([r for r in rows if r['station']==station and study['forecast_training'][0]<=r['date']<=study['forecast_training'][1]],station,asof)
        except ValueError as exc:result['errors'].append(dict(station=station,error=str(exc)));continue
        result['models'][station]=model;result['baseline_models'][station]=baseline;result['features']+=features
        for g in study['groups']:
            if g['station']!=station:continue
            r=next((r for r in features if r['date']==g['date']),None)
            if r is None:continue
            value=prediction(model,r,g['rules']);result['predictions'].append(dict(station=station,date=r['date'],target=r['target'],role=g['role'],**value))
        for role,bounds in [('calibration',study['combination_training']),('test',cfg['profit_test_dates'])]:
            subset=[r for r in features if bounds[0]<=r['date']<=bounds[1] and r['target']>asof]
            errors={method:[r['blend_high_f']+(baseline['bias_f'] if method=='mos' else float(np.array(r['features'])@model['coefficients']))-r['observed_high_f'] for r in subset] for method in ['mos','nowcast']}
            result['metrics'][station+'/'+role]={m:dict(days=len(e),mae=float(np.mean(np.abs(e))) if e else None,rmse=float(np.sqrt(np.mean(np.square(e)))) if e else None) for m,e in errors.items()}
    result.update(created_at=time.time(),source=str(source),history=str(history),source_hashes=source_hashes,profit=None,live_execution=False,limitation='Retrospective prediction inputs. Original METAR receipt/correction history unknown; 30-minute availability delay is assumed. Prediction accuracy is not profit.')
    (dest/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8');(ROOT/'data/us-benter-nowcast-inputs-latest.json').write_text(json.dumps({'directory':str(dest)}),encoding='utf-8')
    print(json.dumps(dict(directory=str(dest),models=list(result['models']),metrics=result['metrics'],errors=result['errors']),indent=2))

if __name__=='__main__':main()
