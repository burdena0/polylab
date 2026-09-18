"""Public Chainlink TWAP relay capture; explicit observation, receipt and gap evidence."""
import json,math,time,threading,gzip,uuid
from decimal import Decimal
import websocket
from .research import ROOT

TOPICS={'crypto_prices_twap_thirty':30,'crypto_prices_twap_sixty':60}

def normalize(message,received_at):
    topic=message.get('topic');p=message.get('payload',{})
    if topic not in TOPICS or message.get('type')!='update' or p.get('symbol')!='btc/usd':return None
    if p.get('window_s')!=TOPICS[topic]:raise ValueError('TWAP window mismatch')
    exact=p.get('full_accuracy_value')
    if not isinstance(exact,str) or not exact.isdigit():raise ValueError('Missing exact E18 price')
    value=Decimal(exact)/Decimal(10**18);observed=float(p['timestamp'])/1000;published=float(message['timestamp'])/1000
    if not value.is_finite() or value<=0 or not all(math.isfinite(x) for x in [observed,published,received_at]) or observed>received_at+5:raise ValueError('Invalid oracle value or timestamp')
    return dict(symbol='btc/usd',window_seconds=TOPICS[topic],value=str(value),observed_at=observed,published_at=published,received_at=received_at,age_seconds=received_at-observed,full_accuracy_value=exact)

class OracleArchive:
    def __init__(self):
        self.root=ROOT/'data/oracle';self.root.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None;self.ws=None
        self.state=dict(running=False,connected=False,messages=0,latest={},source='https://docs.polymarket.com/market-data/chainlink-twap',note='Public relay TWAPs, not independently signature-verified reports or proof of any market settlement rule. Bootstrap frames retain receipt time and never backfill decision-time availability.')
    def snapshot(self):
        with self.lock:
            s=json.loads(json.dumps(self.state))
            for p in s['latest'].values():p['current_age_seconds']=time.time()-p['observed_at']
            return s
    def event(self,kind,**kwargs):
        with (self.root/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(kind=kind,at=time.time(),**kwargs))+'\n')
    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return self.snapshot()
            self.stop_event.clear();self.state['running']=True;self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self.snapshot()
    def stop(self):
        self.stop_event.set()
        if self.ws:self.ws.close()
        if self.thread:self.thread.join(timeout=10)
        return self.snapshot()
    def loop(self):
        total=sum(p.stat().st_size for p in self.root.glob('*.jsonl.gz'))
        try:
            while not self.stop_event.is_set() and total<500_000_000:
                connection=uuid.uuid4().hex;last_ping=0;last_observed={};last_data=time.monotonic()
                try:
                    self.ws=websocket.create_connection('wss://ws-live-data.polymarket.com',timeout=5);self.ws.settimeout(2)
                    self.ws.send(json.dumps(dict(action='subscribe',subscriptions=[dict(topic=t,type='update',filters='{"symbol":"btc/usd"}') for t in TOPICS])))
                    with self.lock:self.state.update(connected=True,connection=connection)
                    self.event('connected',connection=connection)
                    while not self.stop_event.is_set():
                        if time.monotonic()-last_ping>=5:self.ws.send('PING');last_ping=time.monotonic()
                        self.ws.settimeout(min(2,max(.1,5-(time.monotonic()-last_ping))))
                        try:opcode,raw=self.ws.recv_data(control_frame=True)
                        except websocket.WebSocketTimeoutException:
                            if time.monotonic()-last_data>30:raise TimeoutError('No TWAP updates for 30 seconds')
                            continue
                        if opcode==websocket.ABNF.OPCODE_CLOSE:raise ConnectionError('Oracle connection closed')
                        if opcode!=websocket.ABNF.OPCODE_TEXT or not raw:continue
                        if isinstance(raw,bytes):raw=raw.decode('utf-8')
                        if raw in ('PONG','PING'):continue
                        if len(raw)>1_000_000:raise ValueError('Oversized oracle frame')
                        message=json.loads(raw);received=time.time();row=normalize(message,received)
                        if row is None:
                            # Some live relay responses contain a bootstrap array despite the
                            # documented no-replay contract. Preserve it only at receipt time.
                            if isinstance(message.get('payload',{}).get('data'),list):
                                compressed=gzip.compress((json.dumps(dict(kind='bootstrap',received_at=received,connection=connection,message=message))+'\n').encode(),mtime=0)
                                if total+len(compressed)>500_000_000:raise ValueError('Oracle archive reached 500 MB limit')
                                with (self.root/'bootstrap.jsonl.gz').open('ab') as f:f.write(compressed)
                                total+=len(compressed)
                            continue
                        last_data=time.monotonic();window=row['window_seconds'];previous=last_observed.get(window)
                        if previous is not None and row['observed_at']>previous+5:self.event('observation_gap',window=window,start=previous,end=row['observed_at'],connection=connection)
                        if previous is not None and row['observed_at']<=previous:self.event('duplicate_or_out_of_order',window=window,observed_at=row['observed_at'],connection=connection)
                        last_observed[window]=max(previous or 0,row['observed_at']);row['connection']=connection
                        day=time.strftime('%Y-%m-%d',time.gmtime(row['received_at']));compressed=gzip.compress((json.dumps(row)+'\n').encode(),mtime=0)
                        if total+len(compressed)>500_000_000:raise ValueError('Oracle archive reached 500 MB limit')
                        with (self.root/(day+'.jsonl.gz')).open('ab') as f:f.write(compressed)
                        total+=len(compressed)
                        with self.lock:
                            self.state['messages']+=1;self.state['bytes']=total
                            old=self.state['latest'].get(str(window))
                            if old is None or row['observed_at']>old['observed_at']:self.state['latest'][str(window)]=row
                except Exception as exc:
                    with self.lock:self.state.update(connected=False,error=type(exc).__name__+': '+str(exc)[:160])
                    self.event('disconnected',connection=connection,error=str(exc)[:160])
                finally:
                    if self.ws:self.ws.close();self.ws=None
                self.stop_event.wait(10)
        finally:
            with self.lock:self.state.update(running=False,connected=False)
