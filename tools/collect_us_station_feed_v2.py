"""Paired AWC/NWS station poll, first-receipt archive, no market/order client."""
import json,sys,time,hashlib,os,re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_station_feed_v2 import normalize,paired_snapshot

def save(path,obj):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2),encoding='utf-8');tmp.replace(path)

def fetch(name,url,params):
    if url!='https://aviationweather.gov/api/data/metar' and not re.fullmatch(r'https://api.weather.gov/stations/K[A-Z]{3}/observations/latest',url):raise ValueError('Unapproved source')
    start=time.time();clock=time.monotonic()
    with requests.Session() as session:
        session.trust_env=False
        with session.get(url,params=params,headers={'User-Agent':'PolyLab paired US station observation research'},timeout=(5,12),allow_redirects=False,stream=True) as r:
            if 300<=r.status_code<400:raise ValueError('Redirect rejected')
            r.raise_for_status();body=b''
            for chunk in r.iter_content(65536):
                body+=chunk
                if len(body)>2_000_000:raise ValueError('Source byte cap')
            doc=json.loads(body) if body else []
            return name,dict(response=doc,raw_text=body.decode(),receipt=dict(url=r.url,requested_at=start,received_at=time.time(),round_trip_seconds=time.monotonic()-clock,sha256=hashlib.sha256(body).hexdigest(),public_cache_headers={k:r.headers[k] for k in ['Date','Age','Cache-Control','ETag','Last-Modified'] if k in r.headers}))

def once(root,cfg):
    if sum(p.stat().st_size for p in root.rglob('*.json'))>cfg['max_archive_bytes']:raise ValueError('Study archive cap')
    import msvcrt
    with (root/'collector.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):lock.write(b'0');lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return dict(status='duplicate_noop')
        try:
            for name,sha in json.loads((root/'code-freeze.json').read_text())['sha256'].items():
                if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen input changed '+name)
            state_path=root/'state.json';state=json.loads(state_path.read_text()) if state_path.exists() else dict(passes=0,first_receipts={},source_polls={})
            dest=root/'passes'/str(time.time_ns());dest.mkdir(parents=True);started=time.time();save(dest/'start.json',dict(started_at=started,pid=os.getpid()))
            observations=[];errors=[];receipts=[]
            jobs=[('awc','https://aviationweather.gov/api/data/metar',dict(ids=','.join(cfg['stations']),format='json',hours=2))]+[(station,'https://api.weather.gov/stations/'+station+'/observations/latest',None) for station in cfg['stations']]
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures={pool.submit(fetch,*job):job[0] for job in jobs}
                for future in as_completed(futures):
                    name=futures[future]
                    try:
                        name,doc=future.result();save(dest/(name+'.json'),doc);receipts.append(dict(file=name+'.json',**doc['receipt']))
                        source='awc' if name=='awc' else 'nws';values=normalize(doc['response'],doc['receipt'],cfg['stations'],source,None if name=='awc' else name)
                        for value in values:
                            source_key=name;key=source+'|'+value['observation_key']
                            if key not in state['first_receipts']:
                                state['first_receipts'][key]=dict(**value,baseline=source_key not in state['source_polls'],previous_successful_poll=state['source_polls'].get(source_key),receipt_file=str((dest/(name+'.json')).relative_to(root)))
                        observations.extend(values);state['source_polls'][name]=doc['receipt']['received_at']
                    except Exception as exc:errors.append(dict(source=name,error=str(exc)[:200]))
            snapshot=paired_snapshot(observations,cfg['stations']);report=dict(started_at=started,completed_at=time.time(),observations=observations,snapshot=snapshot,receipts=receipts,errors=errors,live_execution=False,profit=None)
            save(dest/'report.json',report);state.update(passes=state['passes']+1,pid=os.getpid(),updated_at=time.time(),latest_pass=str(dest.resolve()));save(state_path,state)
            save(root/'latest.json',dict(directory=str(dest.resolve())))
            return dict(status='partial' if errors else 'complete',directory=str(dest.resolve()),observations=len(observations),awc_newer_stations=[s['station'] for s in snapshot if s['awc_newer_observation_seconds'] and s['awc_newer_observation_seconds']>0],errors=errors,profit=None)
        finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

def main():
    root=Path(sys.argv[1]).resolve();cfg=json.loads((root/'registration.json').read_text());loop='--loop' in sys.argv
    while time.time()<cfg['stop_at']:
        result=once(root,cfg);print(json.dumps(result),flush=True)
        if not loop or result['status']=='duplicate_noop':break
        pause=cfg['poll_interval_seconds'] if not result['errors'] else 300
        time.sleep(min(pause,max(0,cfg['stop_at']-time.time())))

if __name__=='__main__':main()
