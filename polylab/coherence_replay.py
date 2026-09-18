"""Delayed, causal CTF paper replays on the existing immutable BTC sample."""
from dataclasses import asdict
from collections import Counter
import hashlib,json,time,uuid
from .research import ROOT,valid_tick
from .coherence import evaluate,Costs,STRATEGIES

def document(m,t):
    markets=dict(condition=m['condition'],min_shares=m['min_shares'])
    for side,short,token in [('yes','u',m['up']),('no','d',m['down'])]:
        markets[side]=dict(condition=m['condition'],outcome=side,token=token,bid=t['b'+short],ask=t['a'+short],bid_size=t['s'+short],ask_size=t['sa'+short],exchange_at=None)
    return dict(asof=t['t'],markets=[markets],relation={'kind':'binary'})

def replay(markets,strategy,costs=None):
    cfg=Costs(**(costs or {})).validate();cash=cfg.capital;curve=[];ledger=[];reject=Counter()
    for m in sorted(markets,key=lambda m:m['start']):
        decision=m['start']+60;observations=[t for t in m['ticks'] if decision-2<=t['t']<=decision]
        later=[t for t in m['ticks'] if decision+1<=t['t']<=decision+3]
        reason=None
        if not observations or not later or not valid_tick(observations[-1]) or not valid_tick(later[0]):reason='missing_valid_delayed_pair'
        elif cash<1:reason='capital_exhausted'
        else:
            current=asdict(cfg);current['capital']=cash
            try:
                signal=evaluate(strategy,document(m,observations[-1]),current)['best']
                if not signal['eligible']:reason=signal['rejection']
                else:
                    # Commit the signal's direction and size; a later quote cannot choose another basket.
                    fill=evaluate(strategy,document(m,later[0]),current)
                    candidate=next(c for c in fill['candidates'] if c['name']==signal['name'])
                    qty=min(signal['quantity'],candidate['quantity'])
                    net=qty*(candidate['unit_receipt_floor']-candidate['unit_cost'])-cfg.fixed_cost
                    if not candidate['eligible'] or qty<max(x['minimum'] for x in candidate['legs']) or net<cfg.minimum_net:
                        reason='edge_or_depth_lost_before_fill'
                    else:
                        cash+=net
                        ledger.append(dict(condition=m['condition'],name=candidate['name'],signal_at=observations[-1]['t'],fill_at=later[0]['t'],quantity=qty,simulated_pnl=net,capital_committed=qty*candidate['unit_cost']+cfg.fixed_cost,assumption='Hypothetical simultaneous legs and immediate successful CTF conversion. No on-chain transaction or receipt.'))
            except ValueError as exc:reason=str(exc)
        if reason:reject[reason]+=1
        curve.append(dict(t=m['end'],equity=cash,net_equity=cash,drawdown=max(0,cfg.capital-cash)))
    return dict(strategy=strategy,trades=len(ledger),simulated_pnl=cash-cfg.capital,equity=cash,curve=curve,ledger=ledger,rejections=dict(reject),execution_eligible=False)

def run(costs=None):
    # Unknown historical age is an explicit analytical mode, never a fabricated timestamp.
    cfg={'allow_unknown_age':True,**(costs or {})};Costs(**cfg).validate()
    path=ROOT/'data'/'prepared'/'history.json';history=json.loads(path.read_text());markets=sorted(history['markets'],key=lambda m:m['start']);test=markets[int(.8*len(markets)):]
    results={sid:replay(test,sid,cfg) for sid,(kind,mode) in STRATEGIES.items() if kind=='binary'}
    rid=time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:6];directory=ROOT/'data'/'coherence-runs'/rid;directory.mkdir(parents=True)
    report=dict(id=rid,created_at=time.time(),markets=len(test),costs=asdict(Costs(**cfg)),results=results,history_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),limitations=['Cached historical top-of-book; exchange quote age unknown. Strict mode rejects these inputs.','Direction is fixed at 60 seconds, filled at a later observation after at least one second.','Both legs and immediate CTF conversion are hypothetical; capital is released only under that explicit idealization.','Fixed cost is a configurable proxy, not historical gas data. No chain transaction, settlement receipt, or real profit.'],execution_eligible=False)
    (directory/'report.json').write_text(json.dumps(report,allow_nan=False),encoding='utf-8');(ROOT/'data'/'coherence-latest.json').write_text(json.dumps({'id':rid}))
    return report

def latest():
    path=ROOT/'data'/'coherence-latest.json'
    if not path.exists():return {'status':'not_run'}
    return json.loads((ROOT/'data'/'coherence-runs'/json.loads(path.read_text())['id']/'report.json').read_text())

if __name__=='__main__':
    r=run();print(json.dumps(dict(id=r['id'],markets=r['markets'],results={k:{f:v[f] for f in ['trades','simulated_pnl','rejections']} for k,v in r['results'].items()}),indent=2))
