"""Bounded hourly archive of complete member forecasts for actual market stations."""
import hashlib,json,time,threading
import requests
from .research import ROOT

MODELS={'gfs_seamless':31,'ecmwf_ifs025':51,'icon_global':40}

def collect_if_due(stop=None,force=False):
    stop=stop or threading.Event();root=ROOT/'data/ensemble';root.mkdir(parents=True,exist_ok=True);latest=root/'latest.json'
    if latest.exists() and not force:
        previous=json.loads(latest.read_text(encoding='utf-8'))
        if time.time()-previous['started_at']<3600:return previous
    if sum(p.stat().st_size for p in root.rglob('*.json'))>500_000_000:raise ValueError('Ensemble archive reached 500 MB budget')
    source=json.loads((ROOT/'data/public-inputs/latest.json').read_text(encoding='utf-8'));metadata=json.loads((__import__('pathlib').Path(source['directory'])/'station-metadata.json').read_text(encoding='utf-8'))
    dest=root/str(time.time_ns());dest.mkdir();started=time.time();receipts=[]
    for station in metadata[:12]:
        for model,expected in MODELS.items():
            if stop.is_set() or time.time()-started>240:break
            item=dict(station=station['icaoId'],model=model,requested_at=time.time());receipts.append(item)
            params=dict(latitude=station['lat'],longitude=station['lon'],elevation=station['elev'],hourly='temperature_2m',models=model,forecast_days=3,past_days=1,timezone='UTC')
            try:
                chunks=[];size=0
                with requests.get('https://ensemble-api.open-meteo.com/v1/ensemble',params=params,timeout=(5,10),stream=True) as r:
                    r.raise_for_status();item['url']=r.url
                    for chunk in r.iter_content(65536):
                        size+=len(chunk)
                        if size>8_000_000 or time.time()-started>240:raise ValueError('Ensemble response exceeds budget')
                        chunks.append(chunk)
                raw=b''.join(chunks);value=json.loads(raw);keys=[k for k in value['hourly'] if k.startswith('temperature_2m')]
                if len(keys)!=expected:raise ValueError(f'Expected {expected} members; received {len(keys)}')
                name=station['icaoId']+'-'+model+'.json';(dest/name).write_bytes(raw)
                item.update(file=name,available_at=time.time(),sha256=hashlib.sha256(raw).hexdigest(),members=len(keys),hours=len(value['hourly']['time']),requested_coordinates=[station['lat'],station['lon']],returned_grid_coordinates=[value['latitude'],value['longitude']])
            except Exception as exc:item['error']=type(exc).__name__+': '+str(exc)[:180]
            stop.wait(1)
    report=dict(started_at=started,completed_at=time.time(),directory=str(dest),station_source=source['directory'],receipts=receipts,complete=len(receipts)==len(metadata[:12])*len(MODELS) and all('error' not in r for r in receipts),note='Current forecasts, with receipt-time availability. Distinct members remain paired through each local-day maximum/minimum; do not take a maximum of ensemble means. Native model timesteps can be coarser than the interpolated hourly response. No point-in-time historical issue timestamp is inferred.')
    (dest/'receipt.json').write_text(json.dumps(report,indent=2));tmp=root/'latest.tmp';tmp.write_text(json.dumps(report,indent=2));tmp.replace(latest);return report

if __name__=='__main__':
    r=collect_if_due();print(json.dumps(dict(directory=r['directory'],complete=r['complete'],files=len(r['receipts']),errors=[x for x in r['receipts'] if 'error' in x])))
