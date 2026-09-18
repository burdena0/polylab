"""US single-instrument ladder inefficiency screening with explicit legging risk."""
import bisect,hashlib,itertools,json,time
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse,parse_qs
from collections import Counter
from .us_weather import window
from .weather_probability import partition
from .us_replay import normalize_history
from .us_accounting import Account,number,conservative_taker_fee

def snapshot(rules,histories,asof,max_age,max_skew,after=None):
    quotes={}
    for r in rules:
        points=histories.get(r['slug'],[]);i=bisect.bisect_right([p['t'] for p in points],asof)-1
        if i<0 or asof-points[i]['t']>max_age or (after is not None and points[i]['t']<after):return None
        quotes[r['slug']]=points[i]
    stamps=[q['t'] for q in quotes.values()]
    return quotes if max(stamps)-min(stamps)<=max_skew else None

def basket(rules,quotes,side,budget,slippage):
    if side not in ('buy_complete_ladder','short_complete_ladder'):raise ValueError('Unknown basket direction')
    prices=[(number(quotes[r['slug']]['ask']) if side=='buy_complete_ladder' else number(1)-number(quotes[r['slug']]['bid']))+number(slippage) for r in rules]
    if any(not 0<p<1 for p in prices):return None
    qty=int(number(budget)/sum(prices));unit_payoff=1 if side=='buy_complete_ladder' else len(rules)-1
    def leg_costs(q):return [p*q+conservative_taker_fee(p,q) for p in prices]
    while qty and sum(leg_costs(qty))>number(budget):qty-=1
    if not qty:return None
    costs=leg_costs(qty);total=sum(costs);floor=number(qty*unit_payoff);worst_partial=number(0)
    # Every nonempty proper subset can be filled without the remaining legs.
    # Enumerate which valid temperature outcome wins, rather than crediting a
    # complete-ladder floor to a partial position.
    for size in range(1,len(rules)):
        for subset in itertools.combinations(range(len(rules)),size):
            payouts=[sum(qty*(int(i==winner) if side=='buy_complete_ladder' else int(i!=winner)) for i in subset) for winner in range(len(rules))]
            worst_partial=min(worst_partial,number(min(payouts))-sum(costs[i] for i in subset))
    return dict(quantity=qty,cost=str(total),terminal_floor=str(floor),net_floor=str(floor-total),partial_fill_worst_pnl=str(worst_partial),legs=[dict(slug=r['slug'],price=str(p),cost=str(c),quote_t=quotes[r['slug']]['t']) for r,p,c in zip(rules,prices,costs)])

def candidate(group,side,cfg,slippage):
    rules=group['rules'];histories=group['histories'];reasons=Counter();after_t=0;signals=0
    for t in range(group['target']+cfg['decision_start_offset'],group['target']+cfg['decision_end_offset']+1,cfg['decision_grid_seconds']):
        if t<after_t:continue
        quotes=snapshot(rules,histories,t,cfg['max_quote_age_seconds'],cfg['max_leg_skew_seconds'])
        if quotes is None:reasons['incomplete_stale_or_asynchronous_signal']+=1;continue
        order=basket(rules,quotes,side,cfg['entry_budget'],slippage)
        if order is None or number(order['net_floor'])<number(cfg['minimum_net_dollars']):reasons['no_net_floor_after_costs']+=1;continue
        signals+=1;earliest=t+cfg['entry_delay_seconds'];last=earliest+300
        entry_times=sorted({p['t'] for points in histories.values() for p in points if earliest<=p['t']<=last})
        entry_quotes=None;entry_t=last
        for et in entry_times:
            entry_quotes=snapshot(rules,histories,et,cfg['max_quote_age_seconds'],cfg['max_leg_skew_seconds'],after=earliest)
            if entry_quotes is not None:entry_t=et;break
        after_t=entry_t+1
        if entry_quotes is None:reasons['no_delayed_complete_ladder']+=1;continue
        filled=basket(rules,entry_quotes,side,cfg['entry_budget'],slippage)
        if filled is None or number(filled['net_floor'])<number(cfg['minimum_net_dollars']):reasons['floor_disappeared_before_entry']+=1;continue
        return dict(**filled,side=side,date=group['date'],signal_t=t,entry_t=entry_t,signal_net_floor=order['net_floor'],entry_quotes=entry_quotes),dict(reasons),signals
    return None,dict(reasons),signals

def load(root,cfg,project):
    history=project/cfg['history_directory'];registration=history/'registration.json'
    if hashlib.sha256(registration.read_bytes()).hexdigest()!=cfg['history_registration_sha256']:raise ValueError('History registration changed')
    if json.loads((history/'collection.json').read_text())['status']!='complete':raise ValueError('Finish registered history collection')
    groups=[];hashes={};coverage=[]
    for g in cfg['groups']:
        rules=g['rules'];station=rules[0]['station'];day=g['date']
        if any((r['station'],r['date'])!=(station,day) for r in rules):raise ValueError('Mixed settlement definition')
        partition([dict(condition=r['market_id'],unit='F',lower=r['lower'],upper=r['upper']) for r in rules])
        target=int(window(rules[0])[0]-21600);histories={};payouts={}
        for r in rules:
            for kind in ('history','settlement'):
                path=history/(r['market_id']+'-'+kind+'.json');hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest();doc=json.loads(path.read_text());url=urlparse(doc['receipt']['url'])
                if url.scheme!='https' or url.hostname!='gateway.polymarket.us':raise ValueError('Non-US receipt')
                if kind=='history':
                    if url.path!='/v1/price-history' or parse_qs(url.query).get('symbol')!=[r['slug']]:raise ValueError('History mismatch')
                    histories[r['slug']]=normalize_history(doc['response'],target-1800,target+2700)[0]
                else:
                    if url.path!='/v1/markets/'+r['slug']+'/settlement' or doc['response'].get('slug')!=r['slug']:raise ValueError('Settlement mismatch')
                    payout=number(doc['response']['settlement'])
                    if not 0<=payout<=1:raise ValueError('Invalid payout')
                    payouts[r['slug']]=payout
        release=(datetime.fromisoformat(day)+timedelta(days=1)).replace(hour=11,tzinfo=ZoneInfo('America/New_York')).timestamp()
        groups.append(dict(**g,target=target,histories=histories,payouts=payouts,release=release));coverage.append(dict(date=day,contracts=len(rules),price_records=sum(len(x) for x in histories.values()),settlements=len(payouts),unit_payout_verified=sum(payouts.values())==1))
    return groups,hashes,coverage

def run(directory,project):
    root=Path(directory);project=Path(project);cfg=json.loads((root/'registration.json').read_text());groups,hashes,coverage=load(root,cfg,project);results=[]
    first=min(g['target']+cfg['decision_start_offset'] for g in groups);end=max(g['release'] for g in groups)
    for slippage in cfg['slippage_per_side']:
        for side in cfg['strategies']:
            a=Account(cfg['capital'],cfg['reserve']);events=[];orders={};rejections={};intent_count=0;baskets=[];curve=[]
            for g in groups:
                order,reasons,signals=candidate(g,side,cfg,slippage);rejections[g['date']]=reasons;intent_count+=signals
                if order:
                    orders[g['date']]=(order,g);events.extend([(order['entry_t'],1,g['date']),(g['release'],0,g['date'])])
            for t,enter,date in sorted(events):
                order,g=orders[date]
                if enter:
                    actual=basket(g['rules'],order['entry_quotes'],side,min(number(cfg['entry_budget']),a.cash-a.reserve),slippage)
                    if actual is None or number(actual['net_floor'])<number(cfg['minimum_net_dollars']):rejections[date]['portfolio_cash_or_floor']=1;continue
                    for leg in actual['legs']:
                        a.buy(leg['slug'],leg['price'],actual['quantity'],t);a.ledger[-1].update(side=side,signal_t=order['signal_t'],basket_date=date)
                    baskets.append(dict(**actual,date=date,signal_t=order['signal_t'],entry_t=t,completion_assumption='All legs filled at delayed price samples; not fill validated'))
                else:
                    for r in g['rules']:
                        if r['slug'] in a.positions:a.close(r['slug'],g['payouts'][r['slug']] if side=='buy_complete_ladder' else 1-g['payouts'][r['slug']],t,settlement=True)
                s=a.snapshot();curve.append(dict(t=t,cash=float(s['cash']),realized_pnl=float(s['realized_pnl']),open_basis=float(s['open_basis'])))
            s=a.snapshot();expense=cfg['monthly_subscription']*(end-first)/(30*86400)
            results.append(dict(**s,strategy=side,slippage_per_side=slippage,initial_inefficiency_signals=intent_count,completed_basket_scenarios=len(baskets),baskets=baskets,ledger=a.ledger,rejections=rejections,curve=curve,subscription_expense_prorated=expense,realized_after_subscription=float(s['realized_pnl'])-expense,fill_validated=False))
    report=dict(created_at=time.time(),venue='polymarket_us',registration=cfg,coverage=coverage,results=results,period_start=first,period_end=end,source_hashes=hashes,code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),limitations=['Price-history values are display-price proxies; synchronized sample times do not prove executable quotes or historical depth.','Complete exclusive exhaustive temperature rules define a conditional payout floor, not risk-free execution. Partial fills can lose money; worst proper-subset loss is reported for each candidate.','Current fees are counterfactual; no exchange margin optimization or collateral release is assumed.','Cash release is assumed next-day 11AM ET; exact historical settlement timing is unverified.','Only nine NYC dates and a registered 40-minute signal window per day; no broad-market or durable-profit conclusion.'],live_execution=False)
    out=root/('analysis-'+str(time.time_ns()));out.mkdir();(out/'report.json').write_text(json.dumps(report,indent=2));return out,report
