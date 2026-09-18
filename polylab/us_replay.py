"""US display-price feasibility replay; not fill-validated profitability."""
import json,math,bisect,hashlib,time
from collections import Counter
from pathlib import Path
from .us_accounting import Account,number,conservative_taker_fee

def normalize_history(raw,start,end):
    points={};bad=Counter();conflicts=set()
    for row in raw.get('history',[]):
        try:
            t=float(row['timestamp']);ask=float(row['longPrice']);bid=float(number(1)-number(row['shortPrice']))
            if not all(math.isfinite(v) for v in [t,ask,bid]) or t!=int(t) or not start<=t<=end:raise ValueError('time')
            if not 0<bid<=ask<1:raise ValueError('quote')
            point=dict(t=int(t),ask=ask,bid=bid,mid=(ask+bid)/2)
            if t in points and points[t]!=point:conflicts.add(t)
            points[t]=point
        except (KeyError,TypeError,ValueError) as exc:bad[str(exc)]+=1
    for t in conflicts:points.pop(t,None)
    bad['conflicting_timestamps']=len(conflicts)
    return sorted(points.values(),key=lambda p:p['t']),dict(bad)

def opportunity(points,cfg,kind):
    times=[p['t'] for p in points]
    for i,p in enumerate(points):
        j=bisect.bisect_right(times,p['t']-cfg['lookback_seconds'])-1
        if j<0 or p['t']-points[j]['t']>cfg['lookback_seconds']+cfg['max_next_quote_gap_seconds']:continue
        move=p['mid']-points[j]['mid']
        if abs(move)<float(cfg['minimum_move']):continue
        side='long' if (move>0)==(kind=='momentum') else 'short'
        target=p['t']+cfg['entry_delay_seconds'];k=bisect.bisect_left(times,target)
        if k==len(points) or times[k]-target>cfg['max_next_quote_gap_seconds']:continue
        entry=points[k];price=entry['ask'] if side=='long' else 1-entry['bid']
        if not .05<=price<=.95:continue
        exit_target=entry['t']+cfg['hold_seconds'];e=bisect.bisect_left(times,exit_target)
        exit_point=points[e] if e<len(points) and times[e]-exit_target<=cfg['max_next_quote_gap_seconds'] else None
        return dict(signal_t=p['t'],side=side,move=move,entry=entry,exit=exit_point)
    return None

def replay(histories,cfg,kind,slippage,decisions=None,extra_delays=None):
    account=Account(cfg['capital'],cfg['reserve']);events=[];opportunities={};rejected=Counter()
    for slug,points in histories.items():
        o=opportunity(points,cfg,kind)
        if not o:rejected['no_signal_or_delayed_quote']+=1;continue
        if decisions is not None and decisions.get(slug) is not True:rejected['veto_or_missing_decision']+=1;continue
        if extra_delays and extra_delays.get(slug,0)>0:
            target=o['signal_t']+cfg['entry_delay_seconds']+extra_delays[slug]
            times=[p['t'] for p in points];k=bisect.bisect_left(times,target)
            if k==len(points) or times[k]-target>cfg['max_next_quote_gap_seconds']:rejected['agent_delay_quote_missing']+=1;continue
            entry=points[k];exit_target=entry['t']+cfg['hold_seconds'];e=bisect.bisect_left(times,exit_target)
            # Keep the originally reviewed signal and side; never re-signal from
            # later prices under the old agent decision.
            o={**o,'entry':entry,'exit':points[e] if e<len(points) and times[e]-exit_target<=cfg['max_next_quote_gap_seconds'] else None}
        opportunities[slug]=o;events.append((o['entry']['t'],1,slug))
        if o['exit']:events.append((o['exit']['t'],0,slug))
    curve=[dict(t=cfg['start'],realized_pnl=0,open_basis=0,cash=float(account.cash))]
    for t,is_entry,slug in sorted(events):
        o=opportunities[slug]
        if is_entry:
            p=(number(o['entry']['ask']) if o['side']=='long' else number(1)-number(o['entry']['bid']))+number(slippage)
            if not 0<p<1:rejected['invalid_stressed_price']+=1;continue
            budget=min(number(cfg['entry_budget']),account.cash-account.reserve)
            quantity=int(budget/p)
            while quantity and p*quantity+conservative_taker_fee(p,quantity)>budget:quantity-=1
            if not quantity:rejected['reserve_or_minimum_size']+=1;continue
            account.buy(slug,p,quantity,t)
            account.ledger[-1].update(side=o['side'],signal_t=o['signal_t'])
        elif slug in account.positions:
            p=(number(o['exit']['bid']) if o['side']=='long' else number(1)-number(o['exit']['ask']))-number(slippage)
            if not 0<p<1:rejected['invalid_stressed_exit']+=1;continue
            account.close(slug,p,t)
        state=account.snapshot();curve.append(dict(t=t,realized_pnl=float(state['realized_pnl']),open_basis=float(state['open_basis']),cash=float(state['cash'])))
    state=account.snapshot();curve.append(dict(t=cfg['end'],realized_pnl=float(state['realized_pnl']),open_basis=float(state['open_basis']),cash=float(state['cash'])))
    duration=max(0,cfg['end']-cfg['start']);expense=200*duration/(30*86400)
    peak=0;drawdown=0
    for row in curve:peak=max(peak,row['realized_pnl']);drawdown=max(drawdown,peak-row['realized_pnl'])
    state.update(strategy=kind,slippage_per_side=slippage,entries=sum(x['kind']=='buy' for x in account.ledger),exits=sum(x['kind']=='sell' for x in account.ledger),rejected=dict(rejected),curve=curve,ledger=account.ledger,realized_drawdown=drawdown,subscription_expense_prorated=expense,realized_after_prorated_subscription=float(state['realized_pnl'])-expense,liquidation_floor_pnl=float(state['cash'])-float(state['initial_capital']),fill_validated=False)
    return state

def run(directory):
    directory=Path(directory);registration=directory/'registration.json';cfg=json.loads(registration.read_text());histories={};coverage=[]
    for m in cfg['markets']:
        path=directory/(m['id']+'-history.json')
        if not path.exists():coverage.append(dict(slug=m['slug'],status='missing'));continue
        document=json.loads(path.read_text());raw=document['response']
        # The request receipt binds the returned anonymous history to its symbol.
        from urllib.parse import urlparse,parse_qs
        url=urlparse(document['receipt']['url'])
        if url.scheme!='https' or url.hostname!='gateway.polymarket.us' or url.path!='/v1/price-history' or parse_qs(url.query).get('symbol')!=[m['slug']]:raise ValueError('History identity receipt mismatch')
        from datetime import datetime
        end=min(cfg['end'],datetime.fromisoformat(m['endDate'].replace('Z','+00:00')).timestamp())
        points,bad=normalize_history(raw,cfg['start'],end);histories[m['slug']]=points
        settlement=directory/(m['id']+'-settlement.json');verified=None
        if settlement.exists():
            s=json.loads(settlement.read_text())['response']
            if s.get('slug')!=m['slug'] or not 0<=float(s.get('settlement',-1))<=1:raise ValueError('Settlement identity/value mismatch')
            verified=s['settlement']
        coverage.append(dict(slug=m['slug'],category=m.get('category'),points=len(points),rejected=bad,verified_settlement=verified,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    rows=[replay(histories,cfg,kind,slip) for slip in cfg['slippage_per_side'] for kind in ['momentum','mean_reversion']]
    report=dict(venue='polymarket_us',created_at=time.time(),registration_sha256=hashlib.sha256(registration.read_bytes()).hexdigest(),sample_directory=str(directory),coverage=coverage,results=rows,conclusion='Feasibility screen only. Historical display prices are not executions and lack depth, matching order fragmentation and as-of availability. No strategy promotion or claim of validated profitability.',limitations=[cfg['limitation'],'Single sample; parameters frozen before data retrieval, but no independent holdout.','One entry per market; correlated contracts share the same account reserve. Short-side prices use 1 minus the underlying bid/ask.','No outcome is used in signals or exits. Settlement values are coverage checks only; timing is not supplied by this endpoint.','Open positions are not called profit. Chart shows realized P&L; open basis and cash-only liquidation floor are reported separately.','Subscription is a separately reported 200 USD/month expense, prorated using a 30-day month; not deducted twice from the simulated trading account.'])
    dest=directory/('replay-'+str(time.time_ns()));dest.mkdir();(dest/'report.json').write_text(json.dumps(report,indent=2));return dest,report
