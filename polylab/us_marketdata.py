"""Public Polymarket US discovery and book capture. No credentials or order endpoints."""
import json,time,threading,hashlib,re
from collections import Counter
from urllib.parse import quote
from datetime import datetime
import requests
from .research import ROOT

BASE='https://gateway.polymarket.us'

class RateLimited(Exception):
    def __init__(self,retry_after):
        from email.utils import parsedate_to_datetime
        try:delay=float(retry_after)
        except (TypeError,ValueError):
            try:delay=parsedate_to_datetime(retry_after).timestamp()-time.time()
            except Exception:delay=300
        self.retry_after=max(300,delay)
        super().__init__('US gateway rate limited; batch stopped and cooldown retained')

def get(path,params=None):
    if not re.fullmatch(r'/v1/(?:events|search|price-history|markets(?:/[a-zA-Z0-9_-]+/(?:book|settlement))?)',path):raise ValueError('Only public US market-data paths are enabled')
    from .us_transport import reserve,cooldown,check,CoolingDown
    try:
        delay=reserve(ROOT)
        if delay:time.sleep(delay)
        check(ROOT)
    except CoolingDown as exc:raise RateLimited(exc.seconds) from exc
    with requests.Session() as session:
        session.trust_env=False
        requested_at=time.time();request_clock=time.monotonic()
        with session.get(BASE+path,params=params,timeout=(5,10),stream=True,allow_redirects=False) as response:
            if 300<=response.status_code<400:raise ValueError('Unexpected redirect; US host restriction retained')
            if response.status_code==429:
                limited=RateLimited(response.headers.get('Retry-After'));cooldown(ROOT,limited.retry_after);raise limited
            response.raise_for_status();chunks=[];size=0
            for chunk in response.iter_content(65536):
                size+=len(chunk)
                if size>8_000_000:raise ValueError('US response exceeded collection budget')
                chunks.append(chunk)
            raw=b''.join(chunks)
            # Retain only public transport timing/cache fields. HTTP freshness
            # remains separate from the exchange's transactTime and fill depth.
            public_headers={key:response.headers[key] for key in ['Date','Age','Cache-Control','ETag','CF-Cache-Status','Last-Modified'] if key in response.headers}
            return json.loads(raw),dict(url=response.url,requested_at=requested_at,received_at=time.time(),round_trip_seconds=time.monotonic()-request_clock,public_cache_headers=public_headers,sha256=hashlib.sha256(raw).hexdigest())

def normalize_book(raw,slug):
    book=raw['marketData']
    if book['marketSlug']!=slug:raise ValueError('US market slug mismatch')
    def levels(name):
        from decimal import Decimal
        result=[]
        for row in book.get(name,[]):
            if row['px']['currency']!='USD':raise ValueError('US book must use USD')
            p=Decimal(row['px']['value']);q=Decimal(row['qty'])
            if not p.is_finite() or not q.is_finite() or not 0<p<1 or q<=0:raise ValueError('Invalid US price or quantity')
            result.append([float(p),float(q)])
        return sorted(result,reverse=name=='bids')
    bids=levels('bids');offers=levels('offers');stamp=book.get('transactTime')
    t=datetime.fromisoformat(re.sub(r'(\.\d{6})\d+',r'\1',stamp).replace('Z','+00:00')).timestamp() if stamp else None
    return dict(slug=slug,bids=bids,offers=offers,state=book.get('state'),exchange_at=t,valid=bool(bids and offers and bids[0][0]<offers[0][0]),fractional_depth_observed=any(q!=int(q) for p,q in bids+offers),execution_eligible=False,note='Raw archive retains exact decimal quantities. Feed fractions conflict with whole-contract help page; no execution inferred. One US instrument, not independent CTF outcome-token books.')

def collect(stop=None):
    stop=stop or threading.Event();root=ROOT/'data/us';root.mkdir(parents=True,exist_ok=True)
    if sum(p.stat().st_size for p in root.rglob('*.json'))>500_000_000:raise ValueError('US archive reached 500 MB budget')
    cursor_path=root/'discovery-cursor.json'
    cursor=json.loads(cursor_path.read_text()) if cursor_path.exists() else {}
    if time.time()<cursor.get('resume_after',0):return {'cooldown_until':cursor['resume_after']}
    offset=int(cursor.get('offset',0));start_offset=offset
    dest=root/str(time.time_ns());dest.mkdir();markets=[];receipts=[];seen=set();complete=False;started=time.monotonic();errors=[];resume_after=0
    for page in range(8):
        if stop.is_set() or time.monotonic()-started>180:break
        try:
            data,receipt=get('/v1/markets',{'limit':100,'offset':offset,'active':'true','closed':'false'})
        except Exception as exc:
            errors.append(dict(offset=offset,error=str(exc)[:160]))
            if isinstance(exc,RateLimited):resume_after=time.time()+exc.retry_after
            break
        rows=data['markets'];(dest/f'markets-{offset}.json').write_text(json.dumps(data));receipts.append(receipt);offset+=len(rows)
        for m in rows:
            if m['id'] not in seen and m.get('active') is True and m.get('closed') is False:markets.append(m);seen.add(m['id'])
        stop.wait(2)
        if len(rows)<100:complete=True;offset=0;break
    books=[]
    selected=sorted(markets,key=lambda m:(m.get('category')!='weather',m.get('slug','')))[:12]
    for m in selected:
        if stop.is_set() or resume_after or time.monotonic()-started>230:break
        try:
            data,receipt=get('/v1/markets/'+quote(m['slug'],safe='')+'/book');(dest/(m['id']+'-book.json')).write_text(json.dumps(data));receipts.append(receipt)
            books.append(dict(**normalize_book(data,m['slug']),received_at=receipt['received_at']))
        except Exception as exc:
            errors.append(dict(slug=m['slug'],error=str(exc)[:160]))
            if isinstance(exc,RateLimited):resume_after=time.time()+exc.retry_after;break
        stop.wait(2)
    tmp_cursor=root/'discovery-cursor.tmp';tmp_cursor.write_text(json.dumps(dict(offset=offset,resume_after=resume_after)));tmp_cursor.replace(cursor_path)
    report=dict(venue='polymarket_us',created_at=time.time(),directory=str(dest),markets=markets,market_count=len(markets),categories=dict(Counter(m.get('category') or 'unclassified' for m in markets)),discovery_complete=complete,books=books,receipts=receipts,errors=errors,live_execution=False,us_paper_status='Pending US-specific strategy and fill adapters; international results are archived and are not US results')
    report.update(discovery_complete=complete and start_offset==0,pagination_reached_end=complete,start_offset=start_offset,next_offset=offset,resume_after=resume_after,coverage_note='Latest bounded batch only. Offset pagination changes as markets change; archives are not a point-in-time census.')
    (dest/'report.json').write_text(json.dumps(report,indent=2));tmp=root/f'latest-{time.time_ns()}.tmp';tmp.write_text(json.dumps(report));tmp.replace(root/'latest.json');return report

class USCollector:
    def __init__(self):self.stop_event=threading.Event();self.thread=None;self.lock=threading.RLock();self.state=dict(running=False,venue='polymarket_us')
    def snapshot(self):
        with self.lock:
            path=ROOT/'data/us/latest.json';report=json.loads(path.read_text()) if path.exists() else {};return {**report,**self.state}
    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return self.snapshot()
            self.stop_event.clear();self.state['running']=True;self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self.snapshot()
    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=12)
        return self.snapshot()
    def loop(self):
        try:
            while not self.stop_event.is_set():
                try:
                    collect(self.stop_event)
                    with self.lock:self.state.pop('error',None)
                except Exception as exc:
                    with self.lock:self.state['error']=str(exc)[:160]
                self.stop_event.wait(300)
        finally:
            with self.lock:self.state['running']=False
