"""Matched, causal risk-overlay comparisons. Each account starts independently."""
import hashlib,json,math,time,uuid
from collections import Counter
from dataclasses import asdict
import numpy as np
from .research import ROOT,Config,prepare_models,prediction,valid_tick
from .probability import fractional_kelly
from .risk import DrawdownGovernor,liquidity,realized_covariance

VARIANTS={'baseline':'Guide Kelly 10% baseline','kelly_half':'Kelly 5% sensitivity','volatility':'Volatility cap','liquidity':'Exit-depth cap','drawdown':'Drawdown governor','combined':'Combined controls'}

def simulate(rows,model,variant,config=None,target_vol=.002,soft=.08,hard=.15,cooldown=3600):
    if variant not in VARIANTS:raise ValueError('Unknown overlay')
    cfg=Config(**(config or {})).validate();cash=cfg.capital;locked=0.;realized=0.;curve=[];ledger=[];reject=Counter();events=[];peak=cash;max_dd=0.;day=None;day_start=cash
    governor=DrawdownGovernor();risk_on=variant in ('drawdown','combined');last_mode='normal';entry_count=0
    def observe(equity,t):
        nonlocal peak,max_dd,last_mode
        peak=max(peak,equity);max_dd=max(max_dd,peak-equity)
        state=governor.update(equity,t,soft,hard,cooldown)
        if state['mode']!=last_mode:
            if risk_on:events.append(dict(t=t,equity=equity,**state))
            last_mode=state['mode']
        return state if risk_on else dict(mode='normal',size_multiplier=1,flatten=False,cancel_entries=False)
    for row in rows:
        m=row['market'];f=row['features'];stamp=f['time'];p=prediction('momentum-trend-following',f,model)
        if day!=int(stamp//86400):day=int(stamp//86400);day_start=cash
        state=observe(cash,stamp);reason=None
        if p is None:reason='no_signal'
        elif not cfg.allow_unknown_age:reason='unknown_historical_quote_age'
        elif state['cancel_entries']:reason='drawdown_halt'
        elif cash<=day_start*(1-cfg.daily_loss):reason='daily_loss_limit'
        elif f['spread']>cfg.max_spread:reason='spread_limit'
        later=[t for t in m['ticks'] if t['t']>=stamp+cfg.latency]
        entry=later[0] if later else None
        if reason is None and (entry is None or entry['t']>stamp+cfg.latency+2 or not valid_tick(entry)):reason='missing_delayed_quote'
        if reason is None:
            side='u' if p-entry['au']>1-p-entry['ad'] else 'd';prob=p if side=='u' else 1-p
            price=(entry['a'+side]+cfg.slippage)*(1+cfg.fee_bps/10000)
            if not 0<price<1:reason='cost_exceeds_payout'
            else:
                fraction=cfg.kelly/2 if variant=='kelly_half' else cfg.kelly
                budget=min(fractional_kelly(cash,prob,price,fraction),cfg.max_trade,max(0,cfg.capital*cfg.exposure-locked),cash)*state['size_multiplier']
                if variant in ('volatility','combined'):
                    # Only pre-decision quotes; one-second relative-price volatility is not annualized.
                    past=[t for t in m['ticks'] if stamp-30<=t['t']<=stamp]
                    try:
                        cov=realized_covariance([dict(t=t['t'],prices=[(t['b'+side]+t['a'+side])/2]) for t in past],stamp)
                        sigma=math.sqrt(max(0,cov['covariance'][0][0]));budget=min(budget,cfg.capital*target_vol/sigma) if sigma>1e-9 else 0
                    except (ValueError,TypeError):budget=0
                qty=min(budget/price,entry['sa'+side]*.25)
                if variant in ('liquidity','combined'):
                    mid=(entry['a'+side]+entry['b'+side])/2
                    limit=liquidity(dict(mid=mid,bids=[[entry['b'+side],entry['s'+side]]],asks=[[entry['a'+side],entry['sa'+side]]],minimum_shares=m['min_shares'],recent_volume=None))
                    qty=min(qty,limit['maximum_shares'])
                cost=qty*price
                if cost<cfg.min_trade or qty<m['min_shares']:reason='control_or_depth_below_venue_minimum'
                else:
                    cash-=cost;entry_count+=1;remaining=qty;basis=cost;highest=entry['b'+side];intent=None;trimmed=False
                    for t in later[1:]:
                        if not valid_tick(t):continue
                        mark_price=max(0,t['b'+side]-cfg.slippage)*(1-cfg.fee_bps/10000)
                        state=observe(cash+remaining*mark_price,t['t']);highest=max(highest,t['b'+side])
                        if intent and t['t']>=intent['at']+cfg.latency:
                            sell=min(remaining,intent['quantity'])
                            if t['s'+side]>=sell and sell>=m['min_shares']:
                                proceeds=sell*mark_price;sold_basis=basis*(sell/remaining);pnl=proceeds-sold_basis;cash+=proceeds;realized+=pnl;remaining-=sell;basis-=sold_basis
                                ledger.append(dict(condition=m['condition'],side=side,entry_time=entry['t'],intent_time=intent['at'],exit_time=t['t'],reason=intent['reason'],quantity=sell,cost=sold_basis,proceeds=proceeds,pnl=pnl))
                                intent=None
                                if remaining<1e-9:break
                        standard=t['t']>=m['end']-60 or t['b'+side]<entry['a'+side]-.04 or t['b'+side]<highest-.03
                        if intent is None:
                            if state['cancel_entries'] or standard:
                                intent=dict(at=t['t'],quantity=remaining,reason='risk_flatten' if state['cancel_entries'] else 'strategy_exit')
                            elif state['mode']=='reduced' and not trimmed:
                                trim=remaining/2
                                # Odd-lot venue assumptions are not invented. Close all if half is too small.
                                if trim<m['min_shares'] or remaining-trim<m['min_shares']:trim=remaining
                                intent=dict(at=t['t'],quantity=trim,reason='risk_trim');trimmed=True
                        elif state['cancel_entries'] and intent['quantity']<remaining:
                            intent=dict(at=t['t'],quantity=remaining,reason='risk_flatten')
                    if remaining>1e-9:
                        locked+=basis;ledger.append(dict(condition=m['condition'],side=side,entry_time=entry['t'],exit_time=None,quantity=remaining,cost=basis,pnl=None,reason='unresolved_locked'))
        if reason:reject[reason]+=1
        state=observe(cash,m['end']);curve.append(dict(t=m['end'],equity=cash,net_equity=cash,drawdown=peak-cash,locked_basis=locked,governor=state['mode']))
    return dict(name=VARIANTS[variant],variant=variant,trades=entry_count,realized_pnl=realized,equity=cash,open_basis=locked,max_drawdown=max_dd,curve=curve,ledger=ledger,rejections=dict(reject),governor_events=events,execution_eligible=False)

def run(config=None):
    cfg=Config(**(config or {})).validate();path=ROOT/'data'/'prepared'/'history.json';history=json.loads(path.read_text());model,_,_,test=prepare_models(history)
    results={key:simulate(test,model,key,asdict(cfg)) for key in VARIANTS}
    rid=time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:6];out=ROOT/'data'/'risk-runs'/rid;out.mkdir(parents=True)
    report=dict(id=rid,created_at=time.time(),config=asdict(cfg),markets=len(test),results=results,history_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),parameters=dict(target_one_second_portfolio_volatility=.002,soft_drawdown=.08,hard_drawdown=.15,cooldown_seconds=3600),limitations=['Same momentum signals, chronological markets and guide budget; each variant has a separate account.','Historical quote age and fills are unverified; costs and depth participation are assumptions.','Liquidity replay has only top-of-book, no full depth or volume. The evaluator accepts full depth and recent volume.','Covariance is estimated only from pre-decision quotes; volatility is per one-second interval, not annualized.','Drawdown controls use bid-based inventory marks, then delayed sell intents. Flattening can fail on missing depth.','Unexited inventory stays locked and is marked zero after the recorded window.','The control resets its reference peak after cooldown for re-entry while preserving the lifetime high watermark.','This is a repeated retrospective experiment; no independent confirmation of superior performance.'],execution_eligible=False)
    (out/'report.json').write_text(json.dumps(report,allow_nan=False),encoding='utf-8');(ROOT/'data'/'risk-latest.json').write_text(json.dumps({'id':rid}))
    return report

def latest():
    p=ROOT/'data'/'risk-latest.json'
    if not p.exists():return {'status':'not_run'}
    return json.loads((ROOT/'data'/'risk-runs'/json.loads(p.read_text())['id']/'report.json').read_text())

if __name__=='__main__':
    r=run();print(json.dumps(dict(id=r['id'],markets=r['markets'],results={k:{f:v[f] for f in ['trades','realized_pnl','open_basis','max_drawdown']} for k,v in r['results'].items()}),indent=2))
