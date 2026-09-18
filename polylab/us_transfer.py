"""Frozen out-of-city US probability transfer evaluation, no coefficient refits."""
import hashlib,json,time
from pathlib import Path
from .us_mos import fit
from .us_benter import load_groups,simulate,digest

def run_arm(groups,strategy,combination,cfg,slippage):
    adjusted=dict(combination)
    if strategy=='market_recalibrated':adjusted['alpha']=0.
    elif strategy not in ('benter','market_only','mos_only'):raise ValueError('Unregistered transfer arm')
    result=simulate(groups,'benter' if strategy=='market_recalibrated' else strategy,adjusted,cfg,slippage)
    result['strategy']=strategy
    result['combination_weights_used']={k:adjusted[k] for k in ['alpha','beta']} if strategy in ('benter','market_recalibrated') else None
    return result

def run(directory,project):
    root=Path(directory);project=Path(project);cfg=json.loads((root/'registration.json').read_text())
    if json.loads((root/'collection.json').read_text())['status']!='complete':raise ValueError('Finish all registered city/date requests before comparison')
    source=root/'frozen-source-report.json'
    if digest(source)!=cfg['source_study_sha256']:raise ValueError('Frozen NYC source report changed')
    combination=json.loads(source.read_text())['combination_model']
    if combination!=cfg['frozen_combination']:raise ValueError('Transfer weights differ from source registration')
    rows_path=project/cfg['forecast_rows'];rows=json.loads(rows_path.read_text())['rows'];results=[];coverage=[];models={};hashes={}
    for station in cfg['stations']:
        subset={**cfg,'station':station,'groups':[g for g in cfg['groups'] if g['station']==station]}
        if not subset['groups']:raise ValueError('Missing registered station')
        training=[r for r in rows if r['station']==station and cfg['forecast_training'][0]<=r['date']<=cfg['forecast_training'][1]]
        model=fit(training,station,max(r['observation_issued_at'] for r in training)+1);models[station]=model
        groups,covered,source_hashes=load_groups(root,subset,rows,model)
        coverage.extend(dict(station=station,**c) for c in covered);hashes.update(source_hashes)
        if combination['asof']>=min(g['target'] for g in groups):raise ValueError('Source model overlaps transfer decisions')
        for slip in cfg['slippage_per_side']:
            for strategy in cfg['strategies']:
                result=run_arm(groups,strategy,combination,subset,slip);result['station']=station;results.append(result)
    report=dict(created_at=time.time(),venue='polymarket_us',registration=cfg,combination_model=combination,station_forecast_models=models,coverage=coverage,results=results,source_hashes=hashes,source_report_sha256=digest(source),forecast_rows_sha256=digest(rows_path),registration_sha256=digest(root/'registration.json'),code_sha256={name:digest(project/name) for name in ['polylab/us_transfer.py','polylab/us_benter.py','polylab/us_mos.py','polylab/us_weather_replay.py','polylab/us_replay.py','polylab/us_accounting.py']},limitations=['Out-of-city transfer uses the same calendar period as the NYC pilot: correlated weather and market regimes remain; this is not independent temporal replication.','Station temperature errors were summarized previously, but these stations price histories and profit tests were uninspected at registration.','No combination coefficient fitting on transfer data. The alpha=0 arm tests whether independent forecast information adds value.','Historical display-price fills, depth and publication availability remain unverified; current US fees are counterfactual.','Each station/strategy/cost scenario is an independent $50 account with $40 reserve and allocated $200/month expense; results must not be summed as one portfolio.','No automatic live execution or promotion into an existing frozen paper experiment.'],live_execution=False)
    dest=root/('analysis-'+str(time.time_ns()));dest.mkdir();(dest/'report.json').write_text(json.dumps(report,indent=2));return dest,report
