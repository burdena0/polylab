"""Forward-only US paper experiment; public GETs and local simulated accounting."""
import json,time,threading,hashlib,math
from pathlib import Path
from datetime import datetime
from .research import ROOT
from .us_marketdata import get,normalize_book,RateLimited
from .us_accounting import Account,number,conservative_taker_fee

def atomic(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(path)

class Engine:
    def __init__(self,state=None):
        self.accounts={k:Account() for k in ['momentum','mean_reversion']}
        self.history={};self.pending={};self.sides={};self.entered=set();self.processed=0;self.rejected=0
        if state:
            self.history=state['history'];self.pending=state['pending'];self.sides=state['sides'];self.entered=set(state['entered']);self.processed=state['processed'];self.rejected=state['rejected']
            for k,s in state['accounts'].items():
                a=self.accounts[k];a.cash=number(s['cash']);a.realized=number(s['realized']);a.fees=number(s['fees']);a.ledger=s['ledger'];a.positions={slug:{**p,'quantity':number(p['quantity']),'basis':number(p['basis'])} for slug,p in s['positions'].items()};a.snapshot()

    def dump(self):
        accounts={k:dict(cash=str(a.cash),realized=str(a.realized),fees=str(a.fees),ledger=a.ledger,positions={slug:{**p,'quantity':str(p['quantity']),'basis':str(p['basis'])} for slug,p in a.positions.items()}) for k,a in self.accounts.items()}
        return dict(accounts=accounts,history=self.history,pending=self.pending,sides=self.sides,entered=sorted(self.entered),processed=self.processed,rejected=self.rejected)

    def observe(self,book,end_at):
        t=book['received_at'];exchange=book.get('exchange_at');slug=book['slug']
        if not book.get('valid') or book.get('state')!='MARKET_STATE_OPEN' or exchange is None or not 0<=t-exchange<=5:
            self.rejected+=1;return
        history=self.history.setdefault(slug,[])
        if history and t<=history[-1][0]:self.rejected+=1;return
        bid,bq=book['bids'][0];ask,aq=book['offers'][0]
        if not all(math.isfinite(v) for v in [t,bid,bq,ask,aq,end_at]) or not 0<bid<ask<1 or min(bq,aq)<=0:raise ValueError('Invalid paper book')
        self.processed+=1;history.append([t,(bid+ask)/2]);history[:]=[p for p in history if p[0]>=t-1800]
        for kind,a in self.accounts.items():
            key=kind+':'+slug
            if slug in a.positions:
                pos=a.positions[slug]
                if t-pos['entered_at']>=1800:
                    long=self.sides[key]=='long';p=number(bid) if long else number(1)-number(ask);depth=bq if long else aq
                    if int(depth*.25)>=pos['quantity']:a.close(slug,p,t)
                continue
            pending=self.pending.get(key)
            if pending:
                if t-pending['t']>90:del self.pending[key]
                elif t-pending['t']>=2:
                    long=pending['side']=='long';p=number(ask) if long else number(1)-number(bid);depth=aq if long else bq
                    budget=min(number(5),a.cash-a.reserve);q=min(int(budget/p),int(depth*.25))
                    while q and q*p+conservative_taker_fee(p,q)>budget:q-=1
                    del self.pending[key]
                    if q and .05<=p<=.95 and t+1800<end_at:
                        a.buy(slug,p,q,t);self.sides[key]=pending['side'];self.entered.add(key)
                        a.ledger[-1].update(side=pending['side'],signal_t=pending['t'],exchange_at=exchange,fill_assumption='Full simulated taker at next fresh observed top price; <=25% displayed depth; unknown intervening queue and fills')
                        continue
            if key in self.entered or key in self.pending or t+1800>=end_at:continue
            prior=[p for p in history if p[0]<=t-900]
            if not prior or t-prior[-1][0]>1020:continue
            move=history[-1][1]-prior[-1][1]
            if abs(move)<.02:continue
            side='long' if (move>0)==(kind=='momentum') else 'short'
            self.pending[key]=dict(t=t,side=side)

    def settle(self,slug,payout,t):
        p=number(payout)
        if not 0<=p<=1:raise ValueError('Invalid settlement')
        for kind,a in self.accounts.items():
            if slug in a.positions:a.close(slug,p if self.sides[kind+':'+slug]=='long' else number(1)-p,t,settlement=True)

class USPaper:
    def __init__(self):
        self.root=ROOT/'data/us-paper-v1';self.thread=None;self.stop_event=threading.Event();self.lock=threading.RLock();self.state={'running':False};self.engine=Engine();self.registration=None

    def prepare(self):
        self.root.mkdir(exist_ok=True)
        path=self.root/'registration.json'
        code={name:hashlib.sha256((ROOT/'polylab'/name).read_bytes()).hexdigest() for name in ['us_paper.py','us_accounting.py']}
        if path.exists():
            self.registration=json.loads(path.read_text())
            if self.registration['code_sha256']!=code:raise ValueError('US paper code changed; preserve experiment and register a new version')
        else:
            document=json.loads((ROOT/'data/us/paper-discovery.json').read_text());rows=[];now=time.time()
            for m in document['response']['markets']:
                b=m.get('bestBidQuote') or {};a=m.get('bestAskQuote') or {}
                end=datetime.fromisoformat(m['endDate'].replace('Z','+00:00')).timestamp()
                if m.get('active') is not True or m.get('closed') is not False or m.get('status')!='MARKET_STATUS_OPEN' or end<now+1800:continue
                if b.get('currency')!='USD' or a.get('currency')!='USD':continue
                bid,ask=float(b['value']),float(a['value'])
                if .05<=bid<ask<=.95 and ask-bid<=.05:rows.append((ask-bid,m['slug'],m,end))
            selected=[dict(slug=m['slug'],id=m['id'],category=m.get('category'),end_at=end,description=m.get('description'),minimumTradeQty=m.get('minimumTradeQty')) for _,_,m,end in sorted(rows,key=lambda r:(r[0],r[1]))[:6]]
            if not selected:raise ValueError('No eligible public US paper watchlist')
            self.registration=dict(created_at=now,stop_after=now+86400,markets=selected,code_sha256=code,discovery_sha256=hashlib.sha256((ROOT/'data/us/paper-discovery.json').read_bytes()).hexdigest(),initial_capital=50,reserve=40,monthly_subscription=200,strategies=['momentum','mean_reversion'],fee_theta='.0695',lookback_seconds=900,hold_seconds=1800,minimum_move=.02,minimum_delay_seconds=2,pending_expiry_seconds=90,max_exchange_age_seconds=5,depth_fraction=.25,entry_budget=5,quantity_policy='Whole simulated contracts; observed fractional depth retained; no real-execution claim',status='Forward research experiment; previous feasibility losses not a profitable deployment signal',live_execution=False)
            atomic(path,self.registration)
        path=self.root/'state.json'
        if path.exists():self.engine=Engine(json.loads(path.read_text())['engine'])

    def snapshot(self):
        with self.lock:
            now=time.time();start=self.registration['created_at'] if self.registration else now
            accounts=[]
            for kind,a in self.engine.accounts.items():
                s=a.snapshot();expense=200*max(0,min(now,self.registration['stop_after'])-start)/(30*86400) if self.registration else 0
                accounts.append(dict(**s,strategy=kind,entries=sum(r['kind']=='buy' for r in a.ledger),exits=sum(r['kind']!='buy' for r in a.ledger),subscription_expense_prorated=expense,realized_after_subscription=float(s['realized_pnl'])-expense))
            return dict(**self.state,venue='polymarket_us',registration=self.registration,accounts=accounts,processed=self.engine.processed,rejected=self.engine.rejected,live_execution=False,note='Local forward simulation with whole contracts, next fresh book, conservative fees and 25% top-depth cap. No guaranteed fills or verified real profit.')

    def save(self):atomic(self.root/'state.json',dict(saved_at=time.time(),engine=self.engine.dump()))
    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return self.snapshot()
            try:self.prepare()
            except Exception as exc:self.state.update(running=False,error=str(exc)[:180]);return self.snapshot()
            self.stop_event.clear();self.state['running']=True;self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self.snapshot()
    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(12)
    def loop(self):
        try:
            while not self.stop_event.is_set() and time.time()<self.registration['stop_after']:
                if sum(p.stat().st_size for p in self.root.glob('*.jsonl'))>200_000_000:raise ValueError('US paper archive budget reached')
                cooldown=30
                for m in self.registration['markets']:
                    if self.stop_event.is_set():break
                    try:
                        settled=time.time()>=m['end_at']
                        path='/v1/markets/'+m['slug']+('/settlement' if settled else '/book')
                        raw,receipt=get(path)
                        with (self.root/'observations.jsonl').open('a') as f:f.write(json.dumps(dict(raw=raw,receipt=receipt))+'\n')
                        with self.lock:
                            if settled:
                                if raw.get('slug')!=m['slug']:raise ValueError('Settlement identity mismatch')
                                self.engine.settle(m['slug'],raw['settlement'],receipt['received_at'])
                            else:self.engine.observe(dict(**normalize_book(raw,m['slug']),received_at=receipt['received_at']),m['end_at'])
                            self.state['last_receipt_at']=receipt['received_at'];self.state.pop('error',None);self.save()
                    except Exception as exc:
                        with self.lock:self.state['error']=str(exc)[:180]
                        if isinstance(exc,RateLimited):cooldown=exc.retry_after;break
                        if isinstance(exc,ValueError):raise
                    self.stop_event.wait(2)
                self.stop_event.wait(cooldown)
        except Exception as exc:
            with self.lock:self.state['error']=str(exc)[:180]
        finally:
            with self.lock:self.state['running']=False;self.save()
