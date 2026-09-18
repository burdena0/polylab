"""Archive NWS MOS runs and original CLI bulletins from the IEM."""
import sys,time,json,hashlib
from pathlib import Path
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_weather import STATIONS

def main():
    dest=ROOT/'data/us-mos'/str(time.time_ns());dest.mkdir(parents=True)
    registration=dict(created_at=time.time(),stations=list(STATIONS),models=['GFS','NAM'],start='2026-07-27',end='2026-09-18',training_dates=['2026-07-28','2026-08-26'],validation_dates=['2026-08-27','2026-08-31'],test_dates=['2026-09-01','2026-09-16'],cycle='Previous date 12Z',availability_assumption='Nominal runtime plus six hours; original publication/receipt availability is not verified by the MOS JSON archive',method='Mean of GFS and NAM sampled forecast-day highs, station mean-error correction on training dates, normal residual distribution with at least 1F standard deviation',live_execution=False)
    (dest/'registration.json').write_text(json.dumps(registration,indent=2));report=dict(directory=str(dest),receipts=[],errors=[]);deadline=time.monotonic()+235
    with requests.Session() as session:
        session.trust_env=False
        for station in STATIONS:
            jobs=[(station+'-cli.zip','https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py',dict(pil='CLI'+STATIONS[station]['cli'],sdate='2026-07-28T00:00Z',edate='2026-09-18T00:00Z',fmt='zip',limit=200))]
            jobs += [(station+'-'+model+'.json','https://mesonet.agron.iastate.edu/cgi-bin/request/mos.py',dict(station=station,model=model,sts='2026-07-27T00:00Z',ets='2026-09-18T00:00Z',format='json')) for model in registration['models']]
            for name,url,params in jobs:
                if time.monotonic()>deadline:report['errors'].append({'file':name,'error':'Collection time budget reached'});break
                try:
                    with session.get(url,params=params,timeout=(5,20),stream=True,allow_redirects=False) as response:
                        if 300<=response.status_code<400:raise ValueError('Unexpected redirect')
                        response.raise_for_status();chunks=[];size=0
                        for chunk in response.iter_content(65536):
                            size+=len(chunk)
                            if size>12_000_000 or time.monotonic()>deadline:raise ValueError('Archive response budget exceeded')
                            chunks.append(chunk)
                        raw=b''.join(chunks);(dest/name).write_bytes(raw);report['receipts'].append(dict(file=name,url=response.url,received_at=time.time(),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
                except Exception as exc:report['errors'].append(dict(file=name,error=str(exc)[:160]))
                (dest/'collection.json').write_text(json.dumps(report,indent=2));time.sleep(1)
    (dest/'collection.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)

if __name__=='__main__':main()
