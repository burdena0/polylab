"""Registered, serialized prospective NWS/US book archive; never places orders."""
import hashlib,json,re,sys,time,os
from pathlib import Path
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_weather import STATIONS,parse_cli
from polylab.us_marketdata import get,normalize_book,RateLimited
from polylab.us_cli_edge import latest_cli,conditional_direction,assess_quote

def fetch(url):
    if not re.fullmatch(r'https://api.weather.gov/(?:products/types/CLI/locations/[A-Z]{3}|products/[a-f0-9-]{36}|stations/K[A-Z]{3}/observations/latest)',url):raise ValueError('Unapproved public source')
    start=time.time();clock=time.monotonic()
    with requests.Session() as session:
        session.trust_env=False
        with session.get(url,headers={'User-Agent':'PolyLab prospective CLI public research','Accept':'application/geo+json, application/json'},timeout=(5,12),stream=True,allow_redirects=False) as response:
            if 300<=response.status_code<400:raise ValueError('Source redirect rejected')
            response.raise_for_status();body=b''
            for chunk in response.iter_content(65536):
                body+=chunk
                if len(body)>2_000_000:raise ValueError('Source size limit')
            receipt=dict(url=response.url,requested_at=start,received_at=time.time(),round_trip_seconds=time.monotonic()-clock,
                         sha256=hashlib.sha256(body).hexdigest(),public_cache_headers={k:response.headers[k] for k in ['Date','Age','Cache-Control','ETag','Last-Modified'] if k in response.headers})
            return json.loads(body),receipt,body.decode('utf-8')

def save(path,obj):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(obj,indent=2),encoding='utf-8');temp.replace(path)

def once(root):
    cfg=json.loads((root/'registration.json').read_text());now=time.time()
    if now>=cfg['stop_at']:return dict(status='expired',updated_at=now)
    for name,sha in json.loads((root/'code-freeze.json').read_text())['sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen source changed: '+name)
    if sum(p.stat().st_size for p in root.rglob('*.json'))>cfg['max_archive_bytes']:raise ValueError('Registered archive budget reached')
    import msvcrt
    with (root/'collector.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):lock.write(b'0');lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return dict(status='duplicate_noop',updated_at=now)
        try:
            state_path=root/'state.json';state=json.loads(state_path.read_text()) if state_path.exists() else dict(cursor=0,observations=[],passes=0)
            station=cfg['stations'][state['cursor']%len(cfg['stations'])];dest=root/'passes'/str(time.time_ns());dest.mkdir(parents=True)
            started=time.time();deadline=time.monotonic()+cfg['pass_seconds'];report=dict(started_at=started,station=station,receipts=[],observations=[],new_versions=[],quotes=[],errors=[],live_execution=False,positions_opened=0)
            save(dest/'start.json',dict(started_at=started,pid=os.getpid(),station=station))
            def archive(name,url):
                if time.monotonic()>=deadline:raise TimeoutError('Pass time budget')
                doc,receipt,raw_text=fetch(url);save(dest/name,dict(response=doc,receipt=receipt,raw_text=raw_text));report['receipts'].append(dict(file=name,**receipt));return doc,receipt
            try:
                index,_=archive('cli-index.json','https://api.weather.gov/products/types/CLI/locations/'+STATIONS[station]['cli'])
                products=sorted(index['@graph'],key=lambda p:p['issuanceTime'],reverse=True)[:cfg['products_per_station']]
                for item in products:
                    doc,receipt=archive(item['id']+'.json','https://api.weather.gov/products/'+item['id'])
                    observation=parse_cli(doc,station,receipt['received_at']);report['observations'].append(observation)
                    key=(station,observation['product_id'],observation['source_sha256'])
                    known={(o['station'],o['product_id'],o['source_sha256']) for o in state['observations']}
                    if key not in known:
                        prior=[o for o in state['observations'] if (o['station'],o['date'])==(station,observation['date'])]
                        observation.update(receipt_file=str((dest/(item['id']+'.json')).relative_to(root)),first_seen_at=receipt['received_at'])
                        state['observations'].append(observation)
                        report['new_versions'].append(dict(product_id=observation['product_id'],date=observation['date'],first_seen_at=receipt['received_at'],classification='first observation, publication lead unknown' if not prior else 'newly observed version',value_changed=bool(prior) and any((o['max_f'],o['min_f'])!=(observation['max_f'],observation['min_f']) for o in prior)))
                try:
                    doc,receipt=archive('metar-latest.json','https://api.weather.gov/stations/'+station+'/observations/latest')
                    properties=doc['properties'];report['metar']=dict(observed_at=properties.get('timestamp'),received_at=receipt['received_at'],temperature=properties.get('temperature'),role='Covariate only; not contractual CLI settlement and no implied daily extreme')
                except Exception as exc:report['errors'].append(dict(phase='metar',error=str(exc)[:180]))
                signals=[]
                for rule in cfg['rules']:
                    if rule['station']!=station:continue
                    observation=latest_cli(state['observations'],station,rule['date'],time.time())
                    signal=conditional_direction(rule,observation,time.time())
                    if signal:signals.append(signal)
                # Rotate bounded coverage; never pick using future quote prices.
                signals=sorted(signals,key=lambda s:(s['date'],s['slug']))
                offset=(state['passes']//len(cfg['stations']))*cfg['max_books_per_pass']
                if signals:signals=signals[offset%len(signals):]+signals[:offset%len(signals)]
                for signal in signals[:cfg['max_books_per_pass']]:
                    if time.monotonic()>=deadline:report['errors'].append(dict(phase='books',error='Pass time budget'));break
                    raw,receipt=get('/v1/markets/'+signal['slug']+'/book');book=normalize_book(raw,signal['slug']);name=signal['slug']+'-book.json'
                    save(dest/name,dict(response=raw,receipt=receipt,book=book));result=assess_quote(signal,book,receipt,cfg);result['receipt_file']=name;report['quotes'].append(result)
                report['signal_count']=len(signals)
            except Exception as exc:
                report['errors'].append(dict(phase='pass',error=str(exc)[:200]))
                if isinstance(exc,RateLimited):report['resume_after']=time.time()+exc.retry_after
            report.update(completed_at=time.time(),status='partial' if report['errors'] else 'complete',directory=str(dest.resolve()))
            save(dest/'report.json',report)
            state.update(cursor=state['cursor']+1,passes=state['passes']+1,updated_at=time.time(),latest_pass=str(dest.resolve()),last_status=report['status'],pid=os.getpid())
            save(state_path,state);save(root/'latest.json',dict(directory=str(dest.resolve())))
            return dict(directory=str(dest.resolve()),status=report['status'],station=station,observations=len(report['observations']),new_versions=len(report['new_versions']),quotes=len(report['quotes']),qualified=sum(q.get('research_qualified',False) for q in report['quotes']),errors=report['errors'],positions=0)
        finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

def main():
    root=Path(sys.argv[1]).resolve();cfg=json.loads((root/'registration.json').read_text());loop='--loop' in sys.argv
    while time.time()<cfg['stop_at']:
        result=once(root);print(json.dumps(result),flush=True)
        if not loop or result['status']=='duplicate_noop':break
        time.sleep(min(cfg['minimum_pause_seconds'],max(0,cfg['stop_at']-time.time())))

if __name__=='__main__':main()
