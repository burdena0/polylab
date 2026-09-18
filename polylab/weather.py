"""Own weather dataset: one-second full-book states with explicit gaps and provenance."""
from collections import defaultdict
from pathlib import Path
import gzip,json,math,re,threading,time
import websocket
from .marketdata import weather_markets
from .research import ROOT
WS='wss://ws-subscriptions-clob.polymarket.com/ws/market'

def filename(meta):
    city=re.sub(r'[^a-z0-9-]','-',meta['city'].lower()).strip('-')
    return f'{city}-{meta["date"]}.jsonl.gz'

def levels(items):
    result={}
    for item in items:
        p=float(item['price']);s=float(item['size'])
        if not math.isfinite(p+s) or not 0<=p<=1 or s<0:raise ValueError('Invalid book level')
        if s:result[str(p)]=s
    return result

class WeatherArchive:
    def __init__(self):
        self.root=ROOT/'data'/'weather';self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None;self.ws=None;self.books={};self.mapping={};self.connected=False
        p=self.root/'manifest.json'
        self.state=json.loads(p.read_text()) if p.exists() else dict(files={},snapshots=0,gaps=0,started_at=None,updated_at=None,markets=[],last_message='Not started')
        self.state['running']=False;self.state['connected']=False
    def save(self):
        self.state['updated_at']=time.time();tmp=self.root/'manifest.tmp';tmp.write_text(json.dumps(self.state,allow_nan=False),encoding='utf-8');tmp.replace(self.root/'manifest.json')
    def snapshot(self):
        with self.lock:return json.loads(json.dumps(self.state))
    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return self.snapshot()
            self.stop_event.clear();self.state['running']=True;self.state['started_at']=self.state['started_at'] or time.time();self.save()
            self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self.snapshot()
    def stop(self):
        self.stop_event.set()
        if self.ws:self.ws.close()
        if self.thread:self.thread.join(timeout=10)
        with self.lock:self.state['running']=bool(self.thread and self.thread.is_alive());self.save();return self.snapshot()
    def on_open(self,ws):
        with self.lock:self.connected=True;self.state['connected']=True;self.state['last_message']='Streaming public weather books. Recording begins at each initial full snapshot.'
        ws.send(json.dumps({'type':'market','assets_ids':list(self.mapping),'custom_feature_enabled':True}))
    def on_close(self,*args):
        with self.lock:
            self.connected=False;self.books.clear();self.state['connected']=False;self.state['gaps']+=1;self.state['last_message']='Stream disconnected; books invalidated until a new full snapshot.'
    def on_message(self,ws,message):
        if message=='PONG':return
        try:payload=json.loads(message)
        except ValueError:return
        with self.lock:
            for event in payload if isinstance(payload,list) else [payload]:
                kind=event.get('event_type');token=event.get('asset_id');received=time.time()
                if kind=='book' and token in self.mapping:
                    if event.get('market')!=self.mapping[token]['condition']:continue
                    try:
                        self.books[token]=dict(bids=levels(event.get('bids',[])),asks=levels(event.get('asks',[])),exchange_at=float(event['timestamp'])/1000,received_at=received,sequence=1)
                    except (KeyError,ValueError,TypeError):self.books.pop(token,None)
                elif kind=='price_change':
                    for change in event.get('price_changes',[]):
                        token=change.get('asset_id');book=self.books.get(token)
                        if not book or event.get('market')!=self.mapping[token]['condition']:continue
                        try:
                            exchange=float(event['timestamp'])/1000
                            if exchange<book['exchange_at']:self.books.pop(token,None);self.state['gaps']+=1;continue
                            price=float(change['price']);size=float(change['size']);side=change['side']
                            if side not in ('BUY','SELL') or not math.isfinite(price+size) or not 0<=price<=1 or size<0:raise ValueError('Invalid update')
                            target=book['bids' if side=='BUY' else 'asks'];key=str(price)
                            if size:target[key]=size
                            else:target.pop(key,None)
                            book.update(exchange_at=exchange,received_at=received,sequence=book['sequence']+1)
                        except (KeyError,ValueError,TypeError):self.books.pop(token,None)
    def write_snapshots(self):
        now=time.time();groups=defaultdict(list)
        with self.lock:
            if not self.connected:return
            for token,b in self.books.items():
                meta=self.mapping[token];name=filename(meta)
                bids=sorted([[float(p),s] for p,s in b['bids'].items()],reverse=True);asks=sorted([[float(p),s] for p,s in b['asks'].items()])
                valid=bool(bids and asks and bids[0][0]<asks[0][0]);age=now-b['exchange_at']
                # Unchanged books can be old. Age is recorded, never reset by our clock.
                row=dict(schema='polylab.weather.book.v1',snapshot_at=now,exchange_at=b['exchange_at'],received_at=b['received_at'],age_seconds=age,sequence=b['sequence'],valid_book=valid,fresh_for_execution=valid and 0<=age<=5,bids=bids,asks=asks,**meta)
                groups[name].append(json.dumps(row,allow_nan=False))
            for name,lines in groups.items():
                with gzip.open(self.root/name,'at',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
                item=self.state['files'].setdefault(name,dict(name=name,rows=0,first_snapshot=now,city=json.loads(lines[0])['city'],region=json.loads(lines[0])['region'],date=json.loads(lines[0])['date']))
                item.update(rows=item['rows']+len(lines),last_snapshot=now,bytes=(self.root/name).stat().st_size)
                self.state['snapshots']+=len(lines)
            self.state['initialized_books']=len(self.books);self.save()
    def loop(self):
        try:
            last_discovery=0;reader=None;last_ping=0
            while not self.stop_event.is_set():
                if time.time()-last_discovery>300:
                    markets=weather_markets(128);new={m['token']:m for m in markets};last_discovery=time.time()
                    with self.lock:
                        changed=set(new)!=set(self.mapping)
                        if changed:self.books.clear()
                        self.mapping=new;self.state['markets']=markets
                        self.state['coverage_note']='Bounded first 100 weather events, maximum 128 outcome tokens. Live capture only, not complete worldwide history.'
                    if changed and self.ws:self.ws.close()
                if not reader or not reader.is_alive():
                    if not self.mapping:
                        with self.lock:self.state['last_message']='No active daily temperature markets found.';self.save()
                        self.stop_event.wait(15);continue
                    self.ws=websocket.WebSocketApp(WS,on_open=self.on_open,on_message=self.on_message,on_close=self.on_close)
                    reader=threading.Thread(target=self.ws.run_forever,kwargs={'ping_interval':20,'ping_timeout':10},daemon=True);reader.start()
                if self.connected and time.time()-last_ping>10:
                    try:self.ws.send('PING');last_ping=time.time()
                    except Exception:self.on_close()
                self.write_snapshots()
                if sum(x['bytes'] for x in self.state['files'].values())>2_000_000_000:
                    with self.lock:self.state['last_message']='2 GB capture budget reached. Archive preserved; collection stopped.'
                    break
                self.stop_event.wait(1)
        except Exception as exc:
            with self.lock:self.state['last_message']='Weather capture failed: '+type(exc).__name__+': '+str(exc)[:100]
        finally:
            if self.ws:self.ws.close()
            with self.lock:self.state['running']=False;self.save()
    def replay(self,name,offset=0):
        if name not in self.state['files'] or Path(name).name!=name:raise ValueError('Unknown archive')
        rows=[];total=0
        with gzip.open(self.root/name,'rt',encoding='utf-8') as f:
            for i,line in enumerate(f):
                total+=len(line)
                if total>64_000_000:break
                if i>=offset:rows.append(json.loads(line))
                if len(rows)>=200:break
        return dict(rows=rows,offset=offset,file=name,total_rows=self.state['files'][name]['rows'])

    def coherence_pair(self):
        """Read one initialized pair; freshness stays a gate in the evaluator."""
        with self.lock:
            if not self.connected:raise ValueError('Weather stream is disconnected')
            pairs=defaultdict(dict)
            for token,b in self.books.items():
                meta=self.mapping[token];side=meta['outcome'].lower()
                if side not in ['yes','no'] or not b['bids'] or not b['asks']:continue
                bid=max((float(p),s) for p,s in b['bids'].items());ask=min((float(p),s) for p,s in b['asks'].items())
                if bid[0]>=ask[0]:continue
                pairs[meta['condition']][side]=dict(condition=meta['condition'],outcome=side,token=token,bid=bid[0],ask=ask[0],bid_size=bid[1],ask_size=ask[1],exchange_at=b['exchange_at'])
            complete=[(cid,p) for cid,p in pairs.items() if set(p)=={'yes','no'}]
            if not complete:raise ValueError('No initialized valid YES/NO pair available')
            cid,p=max(complete,key=lambda item:min(q['exchange_at'] for q in item[1].values()))
            meta=self.mapping[p['yes']['token']]
            return dict(schema='polylab.coherence.v1',source='Public weather stream: '+meta['question'],asof=time.time(),markets=[dict(condition=cid,min_shares=meta.get('min_shares',5),**p)],relation={'kind':'binary'})

    def probability_quotes(self):
        """Fresh complete binary pairs for a probability scan; never inferred missing legs."""
        with self.lock:
            if not self.connected:return []
            pairs=defaultdict(dict);now=time.time()
            for token,b in self.books.items():
                meta=self.mapping[token];side=meta['outcome'].lower()
                if side not in ['yes','no'] or not b['bids'] or not b['asks'] or not 0<=now-b['exchange_at']<=5 or not 0<=now-b['received_at']<=5:continue
                bid=max((float(p),s) for p,s in b['bids'].items());ask=min((float(p),s) for p,s in b['asks'].items())
                if not 0<bid[0]<ask[0]<1:continue
                pairs[meta['condition']][side]=dict(token=token,bid=bid[0],ask=ask[0],ask_size=ask[1],exchange_at=b['exchange_at'],received_at=b['received_at'],minimum_shares=meta.get('min_shares',5))
            return [dict(condition=cid,yes=p['yes'],no=p['no'],exchange_at=min(x['exchange_at'] for x in p.values()),received_at=min(x['received_at'] for x in p.values()),minimum_shares=max(x['minimum_shares'] for x in p.values())) for cid,p in pairs.items() if set(p)=={'yes','no'} and abs(p['yes']['exchange_at']-p['no']['exchange_at'])<=2]

    def backtest(self,name):
        from .research import features,simulate,Config
        if name not in self.state['files'] or Path(name).name!=name:raise ValueError('Unknown archive')
        grouped=defaultdict(dict);total=0
        with gzip.open(self.root/name,'rt',encoding='utf-8') as f:
            for line in f:
                total+=len(line)
                if total>64_000_000:break
                r=json.loads(line)
                if r['outcome'].lower() not in ('yes','no'):continue
                key=(r['condition'],r['snapshot_at']);grouped[key][r['outcome'].lower()]=r
        conditions=defaultdict(list)
        for (cid,stamp),pair in grouped.items():
            if set(pair)!={'yes','no'}:continue
            # Retain invalid observations as continuity breaks; do not interpolate them.
            tick={'t':stamp}
            for side,name_ in [('u','yes'),('d','no')]:
                r=pair[name_]
                if r['fresh_for_execution']:
                    tick.update({'b'+side:r['bids'][0][0],'a'+side:r['asks'][0][0],'s'+side:r['bids'][0][1],'sa'+side:r['asks'][0][1]})
                else:tick.update({'b'+side:None,'a'+side:None,'s'+side:None,'sa'+side:None})
            conditions[cid].append(tick)
        if not conditions:raise ValueError('No paired Yes/No snapshots recorded')
        cid=sorted(conditions)[0];ticks=sorted(conditions[cid],key=lambda r:r['t'])
        if ticks[-1]['t']-ticks[0]['t']<300:raise ValueError('Need at least five minutes of recorded history for a replay test')
        # Evaluate independent five-minute segments on one selected condition; carry one account.
        rows=[];start=ticks[0]['t'];end=ticks[-1]['t']
        while start+300<=end:
            window=[r for r in ticks if start<=r['t']<start+300]
            m=dict(condition=cid,start=start,end=start+300,ticks=window,min_shares=5,freshness_verified=True)
            feature=features(m)
            if feature:rows.append(dict(market=m,features=feature))
            start+=300
        if not rows:raise ValueError('No complete fresh 60-second decision windows. Stale books remain excluded.')
        cfg=Config(allow_unknown_age=False)
        results={s:simulate(rows,s,{},cfg) for s in ['cash','momentum-trend-following','mean-reversion-on-volatile-markets']}
        report=dict(file=name,condition=cid,windows=len(rows),results=results,created_at=time.time(),note='Price-only weather replay on the first condition by identifier. No meteorological forecast edge or settlement payouts. Live snapshot freshness enforced; gaps are not filled.')
        dest=self.root/'backtests';dest.mkdir(exist_ok=True)
        (dest/(str(time.time_ns())+'.json')).write_text(json.dumps(report,allow_nan=False),encoding='utf-8')
        return report
