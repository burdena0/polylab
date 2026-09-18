"""Five bounded IEM station archives for registered nowcast research."""
import json,time,sys,hashlib
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]

def main():
    dest=ROOT/'data/us-nowcast'/str(time.time_ns());dest.mkdir(parents=True)
    cfg=dict(created_at=time.time(),stations=['KNYC','KMDW','KMIA','KLAX','KSFO'],start='2026-07-28T00:00:00Z',end='2026-09-17T12:00:00Z',
        training_dates=['2026-07-28','2026-08-26'],validation_dates=['2026-08-27','2026-08-31'],test_dates=['2026-09-01','2026-09-16'],profit_test_dates=['2026-09-08','2026-09-16'],
        decision_hour_local_standard=14,observation_delay_seconds=1800,minimum_observations=8,maximum_latest_observation_age_seconds=7200,
        forecast_source='data/us-mos/1789689723727704700',forecast_rows='data/us-mos/1789689723727704700/calibration-1789689900234570400/report.json',
        method='Station ridge residual regression: final CLI high minus GFS/NAM blended high on intercept, latest observed minus interpolated forecast temperature, and observed intraday max minus blended high. Lambda 10 on slopes; unpenalized intercept. Gaussian LOO residual scale floored at 1 F. Baseline prior-day MOS station bias correction.',
        ridge_penalty=10,minimum_training_days=20,monthly_subscription=0,live_execution=False,
        limitations=['Archive is not a record of original local availability or all corrections.','METAR temperatures are predictors, not settlement bounds.','Previously observed CLI labels and market outcomes make this retrospective method exploration.','No profit inferred from prediction accuracy; price, costs and depth need separate tests.'])
    (dest/'registration.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8');report=dict(receipts=[],errors=[],started_at=time.time());deadline=time.monotonic()+235
    with requests.Session() as session:
        session.trust_env=False
        for station in cfg['stations']:
            params=dict(station=station[1:],data=['tmpf','metar'],sts=cfg['start'],ets=cfg['end'],tz='UTC',format='onlycomma',report_type=['3','4'],latlon='no',elev='no',missing='M')
            name=station+'.csv';start=time.time()
            try:
                with session.get('https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py',params=params,headers={'User-Agent':'PolyLab bounded station nowcast research'},timeout=(5,25),stream=True,allow_redirects=False) as r:
                    if r.status_code!=200:raise ValueError('HTTP '+str(r.status_code))
                    raw=b''
                    for chunk in r.iter_content(65536):
                        raw+=chunk
                        if len(raw)>5_000_000 or time.monotonic()>deadline:raise ValueError('Response budget')
                    if b'station,valid,' not in raw[:2000]:raise ValueError('Unexpected archive format')
                    (dest/name).write_bytes(raw);report['receipts'].append(dict(file=name,url=r.url,requested_at=start,received_at=time.time(),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
            except Exception as exc:report['errors'].append(dict(station=station,error=str(exc)))
            (dest/'collection.json').write_text(json.dumps(report,indent=2),encoding='utf-8');time.sleep(1.1)
            if time.monotonic()>deadline:break
    (ROOT/'data/us-nowcast-latest.json').write_text(json.dumps({'directory':str(dest)}),encoding='utf-8');print(json.dumps(dict(directory=str(dest),**report)),flush=True)

if __name__=='__main__':main()
