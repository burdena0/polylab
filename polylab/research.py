"""Causal feature extraction and chronological paper-method experiments."""
from dataclasses import dataclass, asdict
from collections import Counter
from pathlib import Path
import json, math, time, uuid, hashlib
import numpy as np
from .probability import (odds_to_probabilities, fit_logistic, predict_logistic, fit_benter,
                         benter_combine, fractional_kelly, scores, event_ofi, avellaneda_stoikov)
ROOT=Path(__file__).resolve().parents[1]
IMPLEMENTED={
 'cash':'Cash baseline',
 'momentum-trend-following':'Momentum / Trend Following',
 'mean-reversion-on-volatile-markets':'Mean Reversion on Volatile Markets',
 'contrarian-crowd-fade':'Contrarian Crowd-Fade',
 'order-flow-imbalance-microstructure-model':'Order-Flow Imbalance (sampled approximation)',
 'base-rate-exploitation':'Base Rate Exploitation',
 'ensemble-forecast-vs-market-implied-edge':'Ensemble Forecast vs Market-Implied Edge',
 'brier-score-calibration-harvesting':'Brier-Score Calibration Harvesting',
 'yes-no-complement-arbitrage':'Yes/No Complement Arbitrage',
 'normalization':'Basic Odds Normalization',
 'shin':'Shin Odds Probabilities',
 'fundamental':'Book Feature Logistic Model',
 'benter':'Benter Combined Probability',
 'avellaneda-stoikov':'Avellaneda–Stoikov Quote Model',
 'guide-btc-momentum':'Guide BTC 15-minute Momentum'
}
@dataclass(frozen=True)
class Config:
    capital:float=50
    kelly:float=.10
    exposure:float=.15
    daily_loss:float=.05
    max_trade:float=50
    min_trade:float=1
    fee_bps:float=100
    slippage:float=.001
    latency:float=1
    max_spread:float=.08
    allow_unknown_age:bool=True
    monthly_cost:float=0
    def validate(self):
        for key,value in asdict(self).items():
            if key=='allow_unknown_age':
                if type(value) is not bool:raise ValueError('Freshness flag must be boolean')
            elif type(value) not in (float,int) or not math.isfinite(value):raise ValueError('Non-finite configuration')
        if not 0<self.min_trade<=self.max_trade<=10000:raise ValueError('Invalid trade bounds')
        if not 1<=self.capital<=100000 or not 0<self.kelly<=.25 or not 0<self.exposure<=.2 or not 0<self.daily_loss<=.1:raise ValueError('Invalid budget limits')
        if not 0<=self.fee_bps<=1000 or not 0<=self.slippage<=.05 or not 1<=self.latency<=60 or not .001<=self.max_spread<=.2 or not 0<=self.monthly_cost<=10000:raise ValueError('Invalid execution assumptions')
        return self

def valid_tick(r):
    keys=['bu','au','bd','ad','su','sd','sau','sad']
    return all(type(r.get(k)) in (int,float) and math.isfinite(r[k]) for k in keys) and 0<r['bu']<r['au']<1 and 0<r['bd']<r['ad']<1 and all(r[k]>0 for k in keys[4:])

def features(m):
    # Only observations available at the predetermined decision time, never outcome.
    cutoff=m['start']+60
    past=[r for r in m['ticks'] if r['t']<=cutoff]
    if len(past)<20 or cutoff-past[-1]['t']>2 or not all(valid_tick(r) for r in past[-20:]):return None
    if any(b['t']-a['t']>2 for a,b in zip(past[-20:-1],past[-19:])):return None
    last=past[-1];mids=[(r['bu']+r['au'])/2 for r in past[-20:]]
    momentum=mids[-1]-mids[0];vol=float(np.std(np.diff(mids)))
    imbalance=(last['su']-last['sau'])/(last['su']+last['sau'])
    ofi=sum(event_ofi(a,b) for a,b in zip(past[-10:-1],past[-9:]))/max(1,sum(r['su']+r['sau'] for r in past[-10:])/10)
    q=odds_to_probabilities([1/last['au'],1/last['ad']],'normalization')['probabilities'][0]
    try:shin=odds_to_probabilities([1/last['au'],1/last['ad']],'shin')['probabilities'][0]
    except ValueError:shin=None
    vector=[momentum,vol,imbalance,ofi,last['au']-last['bu'],mids[-1]-float(np.mean(mids))]
    return dict(time=cutoff,vector=vector,mid=mids[-1],public=q,shin=shin,momentum=momentum,volatility=vol,imbalance=imbalance,ofi=ofi,spread=last['au']-last['bu'],up_ask=last['au'],down_ask=last['ad'],up_depth=last['sau'],down_depth=last['sad'])

def prepare_models(history):
    all_markets=sorted(history['markets'],key=lambda m:(m['start'],m['condition']))
    a=int(len(all_markets)*.6);b=int(len(all_markets)*.8)
    fit_end=all_markets[a]['start']-86400;cal_end=all_markets[b]['start']-86400
    train=[];cal=[];test=[]
    for i,m in enumerate(all_markets):
        f=features(m)
        if f is None:continue
        row=dict(market=m,features=f)
        if i<a and m['end']<fit_end:train.append(row)
        elif a<=i<b and m['end']<cal_end:cal.append(row)
        elif i>=b:test.append(row)
    if min(len(train),len(cal),len(test))<20:raise ValueError('Insufficient valid chronological samples')
    fundamental=fit_logistic([r['features']['vector'] for r in train],[r['market']['label'] for r in train])
    fcal=[predict_logistic(fundamental,r['features']['vector']) for r in cal];pcal=[r['features']['public'] for r in cal]
    blend=fit_benter([[p,1-p] for p in fcal],[[p,1-p] for p in pcal],[1-r['market']['label'] for r in cal])
    # A separate market-only calibration baseline uses exactly the same calibration set.
    public_cal=fit_logistic([[r['features']['public']] for r in cal],[r['market']['label'] for r in cal])
    model=dict(fundamental=fundamental,benter=blend,public_calibration=public_cal,base_rate=float(np.mean([r['market']['label'] for r in train])),train_n=len(train),calibration_n=len(cal),test_n=len(test),train_end=fit_end,calibration_end=cal_end,test_start=all_markets[b]['start'],embargo_seconds=86400)
    return model,train,cal,test

def prediction(strategy,f,model):
    base=predict_logistic(model['fundamental'],f['vector']) if strategy in ('benter','fundamental','ensemble-forecast-vs-market-implied-edge') else None
    if strategy=='benter':return benter_combine([base,1-base],[f['public'],1-f['public']],model['benter']['alpha'],model['benter']['beta'])[0]
    if strategy=='fundamental':return base
    if strategy=='normalization':return f['public']
    if strategy=='shin':return f['shin']
    if strategy=='base-rate-exploitation':return model['base_rate']
    if strategy=='brier-score-calibration-harvesting':return predict_logistic(model['public_calibration'],[f['public']])
    if strategy=='ensemble-forecast-vs-market-implied-edge':return (base+f['public'])/2
    if strategy=='momentum-trend-following':
        if abs(f['momentum'])<.01:return None
        return float(np.clip(f['mid']+2*f['momentum'],.02,.98))
    if strategy=='mean-reversion-on-volatile-markets':
        if abs(f['vector'][5])<max(.01,2*f['volatility']):return None
        return float(np.clip(f['mid']-3*f['vector'][5],.02,.98))
    if strategy=='contrarian-crowd-fade':return float(np.clip(.5-.5*(f['public']-.5),.05,.95)) if abs(f['public']-.5)>.2 else None
    if strategy=='order-flow-imbalance-microstructure-model':return float(np.clip(f['public']+.05*np.tanh(f['ofi']),.02,.98)) if abs(f['ofi'])>.5 else None
    return None

def packet(row,model, strategy='benter'):
    f=row['features'];p=prediction(strategy,f,model)
    # No identity, date, outcome, future quotes, future P&L, or training text.
    return dict(probability_up=p,market_probability=f['public'],momentum=f['momentum'],volatility=f['volatility'],imbalance=f['imbalance'],spread=f['spread'],up_ask=f['up_ask'],down_ask=f['down_ask'],up_depth=f['up_depth'],down_depth=f['down_depth'],quote_freshness='unknown',source='cached top-of-book; research simulation only',calibration_samples=model['calibration_n'])

def simulate(rows,strategy,model,cfg=Config(),decisions=None,latencies=None):
    cfg.validate();cash=cfg.capital;locked=0.;realized=0.;peak=cfg.capital;max_dd=0.;ledger=[];curve=[];reject=Counter();trades=0;wins=0;day=None;day_equity=cash;latencies=latencies or {}
    start=rows[0]['market']['start'] if rows else 0
    for idx,row in enumerate(rows):
        m=row['market'];f=row['features'];stamp=f['time'];p=prediction(strategy,f,model)
        current_day=int(stamp//86400)
        if current_day!=day:day=current_day;day_equity=cash
        reason=None
        if strategy in ('cash','avellaneda-stoikov','guide-btc-momentum'):reason='baseline_or_missing_required_feed'
        elif not cfg.allow_unknown_age and not m.get('freshness_verified'):reason='quote_freshness_unknown'
        elif decisions is not None and decisions.get(str(idx)) is not True:reason='agent_veto_or_missing_decision'
        elif cash<=day_equity*(1-cfg.daily_loss):reason='daily_loss_limit'
        elif f['spread']>cfg.max_spread:reason='spread_limit'
        elif p is None and strategy!='yes-no-complement-arbitrage':reason='no_signal'
        delay=max(cfg.latency,latencies.get(str(idx),0))
        candidates=[t for t in m['ticks'] if t['t']>=stamp+delay]
        entry=candidates[0] if candidates else None
        if reason is None and (entry is None or entry['t']>stamp+delay+2 or not valid_tick(entry)):reason='missing_delayed_book'
        if reason is None and entry['t']>=m['end']-30:reason='too_late'
        if reason is None:
            pair=strategy=='yes-no-complement-arbitrage'
            if pair:
                # Fully collateralized split/sell direction from the source description.
                proceeds=(max(0,entry['bu']-cfg.slippage)+max(0,entry['bd']-cfg.slippage))*(1-cfg.fee_bps/10000)
                if proceeds<=1.002:reason='no_complement_edge'
                else:
                    quantity=min(cfg.capital*cfg.exposure-locked,cash,cfg.max_trade,entry['su']*.25,entry['sd']*.25)
                    if quantity<m['min_shares']:reason='insufficient_collateral_or_depth'
                    else:
                        pnl=quantity*(proceeds-1);cash+=pnl;realized+=pnl;trades+=1;wins+=1
                        ledger.append(dict(condition=m['condition'],side='SPLIT_AND_SELL_PAIR',entry_time=entry['t'],exit_time=entry['t'],quantity=quantity,cost=quantity,proceeds=quantity*proceeds,pnl=pnl,assumption='Idealized simultaneous legs and immediate collateral split; no atomic fill proof or gas history'))
            else:
                side='u' if p-entry['au']>1-p-entry['ad'] else 'd';prob=p if side=='u' else 1-p
                price=min(.999999,entry['a'+side]+cfg.slippage)*(1+cfg.fee_bps/10000)
                if not 0<price<1:reason='cost_exceeds_payout'
                else:
                    budget=min(fractional_kelly(cash,prob,price,cfg.kelly),cfg.max_trade,max(0,cfg.capital*cfg.exposure-locked),cash)
                    quantity=min(budget/price,entry['sa'+side]*.25)
                    cost=quantity*price
                    if cost<cfg.min_trade or quantity<m['min_shares']:reason='kelly_below_minimum_or_depth'
                    else:
                        cash-=cost;trades+=1;exit_tick=None;highest=entry['b'+side];intent=None
                        for t in candidates[1:]:
                            if not valid_tick(t):continue
                            highest=max(highest,t['b'+side])
                            # Intent followed by a later book, including time-based exits.
                            if intent is not None and t['t']>=intent+cfg.latency and t['s'+side]>=quantity:
                                exit_tick=t;break
                            if t['t']>=m['start']+240 or t['b'+side]<entry['a'+side]-.04 or (strategy=='momentum-trend-following' and t['b'+side]<highest-.03):
                                intent=intent or t['t']
                        if exit_tick:
                            value=quantity*max(0,exit_tick['b'+side]-cfg.slippage)*(1-cfg.fee_bps/10000);pnl=value-cost;cash+=value;realized+=pnl;wins+=pnl>0
                        else:value=0.;pnl=None;locked+=cost
                        ledger.append(dict(condition=m['condition'],side='UP' if side=='u' else 'DOWN',entry_time=entry['t'],exit_time=exit_tick['t'] if exit_tick else None,quantity=quantity,cost=cost,proceeds=value if exit_tick else None,pnl=pnl,status='closed' if exit_tick else 'open_unmarked'))
        if reason:reject[reason]+=1
        equity=cash # unresolved inventory is marked at zero, with basis separately disclosed
        peak=max(peak,equity);dd=peak-equity;max_dd=max(max_dd,dd)
        expense=cfg.monthly_cost*(m['end']-start)/(30*86400)
        curve.append(dict(t=m['end'],equity=equity,net_equity=equity-expense,drawdown=dd,realized=realized,cash=cash,locked_basis=locked,condition=m['condition']))
    return dict(strategy=strategy,name=IMPLEMENTED[strategy],equity=cash,realized_pnl=realized,net_pnl=cash-cfg.capital-(curve[-1]['equity']-curve[-1]['net_equity'] if curve else 0),return_pct=(cash/cfg.capital-1)*100,max_drawdown=max_dd,trades=trades,wins=wins,open_basis=locked,curve=curve,ledger=ledger,rejections=dict(reject),execution_eligible=False)

def run(config=None,agent=None):
    cfg=Config(**(config or {})).validate()
    path=ROOT/'data'/'prepared'/'history.json';history=json.loads(path.read_text())
    model,train,cal,test=prepare_models(history)
    results={s:simulate(test,s,model,cfg) for s in IMPLEMENTED}
    scorecard={}
    for s in IMPLEMENTED:
        pairs=[(prediction(s,r['features'],model),r['market']['label']) for r in test]
        pairs=[(p,y) for p,y in pairs if p is not None]
        if pairs:scorecard[s]=scores([p for p,y in pairs],[y for p,y in pairs])
    ablation=None
    if agent and agent.get('history_sha256')==hashlib.sha256(path.read_bytes()).hexdigest():
        ids=agent['test_indices']; subset=[test[i] for i in ids]
        source=agent.get('strategy','benter')
        decision={str(i):agent['decisions'].get(str(original),{}).get('allow',False) for i,original in enumerate(ids)}
        latency={str(i):agent['decisions'].get(str(original),{}).get('latency_seconds',60) for i,original in enumerate(ids)}
        filtered={str(i):r['features']['spread']<=.04 and r['features']['volatility']<=.02 for i,r in enumerate(subset)}
        ablation=dict(model=agent['model'],n=len(subset),strategy=source,without=simulate(subset,source,model,cfg),with_agent=simulate(subset,source,model,cfg,decision),with_latency=simulate(subset,source,model,cfg,decision,latency),rule_filter=simulate(subset,source,model,cfg,filtered),decision_count=len(agent['decisions']),failures=agent.get('failures',[]),latency_mean=float(np.mean(list(latency.values()))),valid_decisions=sum(isinstance(d.get('allow'),bool) for d in agent['decisions'].values()))
        diffs=np.array([a['equity']-b['equity'] for a,b in zip(ablation['with_agent']['curve'],ablation['without']['curve'])])
        ablation['equity_difference']=float(diffs[-1]) if len(diffs) else 0
        # Paired bootstrap of per-market increments, not a fabricated Sharpe ratio.
        increments=np.diff(np.r_[0,diffs]);rng=np.random.default_rng(731)
        samples=[float(rng.choice(increments,len(increments),replace=True).sum()) for _ in range(1000)] if len(increments) else [0]
        ablation['paired_bootstrap_95']=np.quantile(samples,[.025,.975]).tolist()
        ablation['conclusion']='Exploratory paired sample; no demonstrated general agent advantage.'
    runid=time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:6]
    report=dict(id=runid,created_at=time.time(),config=asdict(cfg),model=model,results=results,scores=scorecard,ablation=ablation,history_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source=history['source'],coverage=dict(selected=len(history['markets'])+len(history['failed']),verified=len(history['markets']),failed=len(history['failed']),ticks=sum(len(m['ticks']) for m in history['markets']),test_markets=len(test)),limitations=['One-second cached quotes: exchange freshness and intervening fills are unknown.','Five-minute BTC archive does not reproduce the guide’s fifteen-minute BTC oracle signal.','All fills are hypothetical, capped at 25% of displayed size; fees and slippage are assumptions.','Training uses verified final outcomes with a one-day embargo, but historical resolution publication times are unavailable.','No settlement payouts are booked; unsold inventory remains locked and marked at zero.','Shin bookmaker assumptions may not apply to two exchange ask quotes.','Benter is adapted to a book-feature model; this is not a replication of horse-racing returns.','Retrospective evaluation and repeated experiments can overfit; no live profitability established.'],execution_eligible=False)
    frozen=ROOT/'data'/'datasets'/(report['history_sha256']+'.json');frozen.parent.mkdir(exist_ok=True)
    if not frozen.exists():frozen.write_bytes(path.read_bytes())
    report['frozen_dataset']=str(frozen.relative_to(ROOT))
    out=ROOT/'data'/'runs'/runid;out.mkdir(parents=True,exist_ok=False)
    (out/'report.json').write_text(json.dumps(report,allow_nan=False),encoding='utf-8')
    (ROOT/'data'/'latest.json').write_text(json.dumps({'id':runid}),encoding='utf-8')
    return report

if __name__=='__main__':
    agent_path=ROOT/'data'/'agent-comparison-momentum.json'
    if not agent_path.exists():agent_path=ROOT/'data'/'agent-comparison.json'
    r=run(agent=json.loads(agent_path.read_text()) if agent_path.exists() else None)
    print(json.dumps({'id':r['id'],'coverage':r['coverage'],'results':{k:{f:v[f] for f in ['trades','realized_pnl','open_basis']} for k,v in r['results'].items()}},indent=2))
