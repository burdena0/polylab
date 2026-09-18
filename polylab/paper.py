"""Persistent, local-only paper portfolio and public BTC capture loop."""
import json,time,threading,uuid
from .research import ROOT,Config,prepare_models,features,prediction,valid_tick
from .probability import fractional_kelly
from .marketdata import btc_market,btc_tick
from .fees import validate as validate_fee,fee_usdc,unit_cost

class PaperTrader:
    def __init__(self,strategy='benter',interval=300,risk_profile=None):
        self.strategy=strategy;self.interval=interval;self.risk_profile=risk_profile
        if strategy not in ('benter','guide-btc-momentum','momentum-trend-following') or risk_profile not in (None,'liquidity'):raise ValueError('Unsupported paper configuration')
        account='paper-benter-fee-v2' if strategy=='benter' else 'paper-guide-fee-v2' if strategy=='guide-btc-momentum' else 'paper-momentum-'+(risk_profile or 'baseline')+'-fee-v2'
        self.path=ROOT/'data'/account/'state.json';self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None
        self.state=json.loads(self.path.read_text()) if self.path.exists() else dict(cash=50.,realized_pnl=0.,positions=[],snapshots=0,journal=[],strategy=strategy,decided=[],day=None,day_start=50.,running=False)
        self.state['running']=False
        self.state['fee_model']='Observed Gamma feeSchedule curve; taker USDC fees rounded to 5 decimals; rebates excluded'
        self.state.update(account_id=account,risk_profile=risk_profile,label='Momentum + exit-depth cap' if risk_profile else 'Momentum baseline' if strategy=='momentum-trend-following' else strategy)
        self.cfg=Config(allow_unknown_age=False)
    def save(self):
        self.state['updated_at']=time.time();tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.state,allow_nan=False),encoding='utf-8');tmp.replace(self.path)
    def log(self,msg):
        self.state['last_message']=msg;self.state['journal'].append(dict(t=time.time(),message=msg));self.state['journal']=self.state['journal'][-200:]
    def record_trade(self,event):
        with (self.path.parent/'trades.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event,allow_nan=False)+'\n')
    def snapshot(self):
        with self.lock:return json.loads(json.dumps(self.state))
    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return self.snapshot()
            self.stop_event.clear();self.state['running']=True;self.log('Starting public-data paper trader. No exchange orders.');self.save()
            self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self.snapshot()
    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=12)
        with self.lock:self.state['running']=bool(self.thread and self.thread.is_alive());self.log('Paper trader stopping; open simulated positions preserved.');self.save();return self.snapshot()
    def step(self,m,t,model):
        s=self.state;cfg=self.cfg;day=int(t['t']//86400)
        fee_schedule=validate_fee(m.get('fee_schedule'),m['condition'],t['t'])
        if day!=s['day']:s['day']=day;s['day_start']=s['cash']
        for p in s['positions'][:]:
            if p['condition']!=m['condition']:continue
            p['highest_bid']=max(p.get('highest_bid',p['entry_price']),t['b'+p['side']])
            if p.get('exit_intent') and t['t']>=p['exit_intent']+cfg.latency and t['s'+p['side']]>=p['quantity']:
                exit_price=max(0,t['b'+p['side']]-cfg.slippage);fee=fee_usdc(p['quantity'],exit_price,fee_schedule)
                proceeds=max(0,p['quantity']*exit_price-fee)
                pnl=proceeds-p['cost'];s['cash']+=proceeds;s['realized_pnl']+=pnl;s['positions'].remove(p);self.log(f'Paper exit {p["side"].upper()}: P&L {pnl:.4f}')
                self.record_trade(dict(kind='exit',t=t['t'],condition=m['condition'],side=p['side'],quantity=p['quantity'],cost=p['cost'],proceeds=proceeds,pnl=pnl,fee=fee,fee_schedule=fee_schedule))
            elif t['t']>=m['end']-60 or t['b'+p['side']]<p['entry_price']-.04 or (self.strategy=='momentum-trend-following' and t['b'+p['side']]<p['highest_bid']-.03):p['exit_intent']=p.get('exit_intent') or t['t']
        pending=s.get('pending')
        if pending and pending['condition']==m['condition'] and t['t']>=pending['intent']+cfg.latency:
            s['pending']=None
            side=pending['side'];execution_price=t['a'+side]+cfg.slippage;price=unit_cost(execution_price,fee_schedule)
            if not 0<price<1 or t['t']>=m['end']-30:return
            locked=sum(p['cost'] for p in s['positions']);budget=min(fractional_kelly(s['cash'],pending['p'],price,cfg.kelly),max(0,cfg.capital*cfg.exposure-locked),s['cash'],cfg.max_trade)
            # Reserve a fee-rounding quantum so an upward-rounded fee cannot exceed budget.
            quantity=min(max(0,budget-.00001)/price,t['sa'+side]*.25)
            if self.risk_profile=='liquidity':
                from .risk import liquidity
                limit=liquidity(dict(mid=(t['a'+side]+t['b'+side])/2,bids=[[t['b'+side],t['s'+side]]],asks=[[t['a'+side],t['sa'+side]]],recent_volume=None,minimum_shares=m['min_shares']))
                quantity=min(quantity,limit['maximum_shares'])
            fee=fee_usdc(quantity,execution_price,fee_schedule);cost=quantity*execution_price+fee
            if cost<cfg.min_trade or quantity<m['min_shares']:self.log('No paper entry: Kelly budget or displayed size below venue minimum.');return
            if s['cash']<=s['day_start']*(1-cfg.daily_loss):self.log('No paper entry: daily loss limit.');return
            s['cash']-=cost;s['positions'].append(dict(condition=m['condition'],side=side,quantity=quantity,cost=cost,entry_price=t['a'+side],highest_bid=t['b'+side],entered_at=t['t']))
            self.record_trade(dict(kind='entry',t=t['t'],condition=m['condition'],side=side,quantity=quantity,cost=cost,proceeds=None,pnl=None,fee=fee,fee_schedule=fee_schedule))
            self.log(f'Paper entry {side.upper()}: {quantity:.4f} shares, cost {cost:.4f}')
        if m['condition'] not in s['decided'] and t['t']>=m['start']+60:
            if self.strategy=='guide-btc-momentum':
                from .guide import observe
                signal=observe((t['bu']+t['au'])/2);s['source_signal']=signal;p=signal['probability_up'];f={'spread':t['au']-t['bu']}
                s['decided'].append(m['condition']);s['decided']=s['decided'][-500:]
                if p is None:self.log('No guide entry: underlying BTC momentum below the required edge threshold.');return
            else:
                s['decided'].append(m['condition']);s['decided']=s['decided'][-500:]
                f=features(m)
                if f is None:self.log('No paper signal: complete pre-decision history unavailable.');return
                p=prediction(self.strategy,f,model)
                if p is None:self.log('No paper entry: strategy has no qualifying signal.');return
            side='u' if p-t['au']>1-p-t['ad'] else 'd';prob=p if side=='u' else 1-p
            if f['spread']>cfg.max_spread:self.log('No paper signal: spread limit.');return
            s['pending']=dict(condition=m['condition'],side=side,p=prob,intent=t['t'])
            self.log(f'Recorded a {self.strategy} paper intent; waiting for a later fresh book.')
    def loop(self):
        try:
            history=json.loads((ROOT/'data'/'prepared'/'history.json').read_text());model,_,_,_=prepare_models(history)
            current=None
            while not self.stop_event.is_set():
                try:
                    now=time.time()
                    if current is None or now>=current['end']:
                        current=btc_market(self.interval);
                        if current:
                            with (self.path.parent/'markets.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(current,allow_nan=False)+'\n')
                            current['ticks']=[]
                    if current is None:
                        with self.lock:self.log('No current BTC market published; retrying.');self.save()
                        self.stop_event.wait(10);continue
                    tick=btc_tick(current);current['ticks'].append(tick)
                    with (self.path.parent/'observations.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(condition=current['condition'],**tick))+'\n')
                    with self.lock:
                        self.state['snapshots']+=1;self.state['market']={k:v for k,v in current.items() if k!='ticks'}
                        self.step(current,tick,model)
                        if not self.state.get('last_message'):self.log('Receiving fresh public BTC books.')
                        self.save()
                except Exception as exc:
                    with self.lock:self.log(f'Public data unavailable: {type(exc).__name__}: {str(exc)[:120]}');self.save()
                    self.stop_event.wait(5)
                self.stop_event.wait(1)
        except Exception as exc:
            with self.lock:self.log('Paper worker failed: '+type(exc).__name__)
        finally:
            with self.lock:self.state['running']=False;self.save()
