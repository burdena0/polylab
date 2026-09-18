"""Historical US MOS forecast-edge scenario with globally ordered cash flows."""
import json,time,hashlib,bisect
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse,parse_qs
from .us_weather import window
from .us_mos import predict
from .us_replay import normalize_history
from .us_accounting import Account,number,conservative_taker_fee

def choose_entry(rules,probabilities,histories,target,delay,max_age,budget,threshold,slippage):
    signals={};times={}
    for rule in rules:
        slug=rule['slug'];points=histories.get(slug,[]);ts=[p['t'] for p in points];i=bisect.bisect_right(ts,target)-1
        if i<0 or target-ts[i]>max_age:return None,'Incomplete contemporaneous ladder'
        signals[slug]=points[i];times[slug]=ts
    candidates=[]
    for rule in rules:
        slug=rule['slug'];point=signals[slug];prob=probabilities[rule['market_id']]
        for side,p,price in [('long',prob,number(point['ask'])),('short',1-prob,number(1)-number(point['bid']))]:
            price+=number(slippage)
            if not 0<price<1:continue
            q=int(number(budget)/price)
            while q and q*price+conservative_taker_fee(price,q)>number(budget):q-=1
            if not q:continue
            ev=number(p)*q-q*price-conservative_taker_fee(price,q)
            if ev>=number(threshold):candidates.append((float(ev),slug,side,p))
    if not candidates:return None,'No forecast edge after scenario costs'
    # Decide once using signal-time prices, not the subsequent entry price.
    ev,slug,side,p=sorted(candidates,key=lambda r:(-r[0],r[1],r[2]))[0]
    ts=times[slug];i=bisect.bisect_left(ts,target+delay)
    if i==len(ts) or ts[i]-(target+delay)>max_age:return None,'No delayed quote for selected contract'
    point=histories[slug][i];price=(number(point['ask']) if side=='long' else number(1)-number(point['bid']))+number(slippage)
    if not 0<price<1:return None,'Invalid stressed entry price'
    quantity=int(number(budget)/price)
    while quantity and quantity*price+conservative_taker_fee(price,quantity)>number(budget):quantity-=1
    if not quantity or number(p)*quantity-quantity*price-conservative_taker_fee(price,quantity)<number(threshold):return None,'Edge disappeared before delayed entry'
    return dict(slug=slug,side=side,signal_t=target,entry_t=point['t'],price=str(price),probability=p,signal_expected_dollars=ev),'candidate'

def run(history_dir,calibration_dir):
    history_dir=Path(history_dir);calibration_dir=Path(calibration_dir);cfg=json.loads((history_dir/'registration.json').read_text());cal=json.loads((calibration_dir/'report.json').read_text())
    rowmap={(r['station'],r['date']):r for r in cal['rows']};groups=[];coverage=[];source_hashes={}
    for group in cfg['groups']:
        rules=group['rules'];station=rules[0]['station'];date=group['date'];target=int(window(rules[0])[0]-cfg['decision_seconds_before_climate_day_start']);histories={};payouts={};errors=[]
        for rule in rules:
            for kind in ['history','settlement']:
                path=history_dir/(rule['market_id']+'-'+kind+'.json')
                if not path.exists():errors.append(rule['slug']+': missing '+kind);continue
                source_hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest();doc=json.loads(path.read_text());url=urlparse(doc['receipt']['url'])
                if url.scheme!='https' or url.hostname!='gateway.polymarket.us':raise ValueError('Wrong venue history receipt')
                if kind=='history':
                    if url.path!='/v1/price-history' or parse_qs(url.query).get('symbol')!=[rule['slug']]:raise ValueError('Weather history identity mismatch')
                    points,rejected=normalize_history(doc['response'],target-1800,target+2700);histories[rule['slug']]=points
                    if not points:errors.append(rule['slug']+': no usable price history')
                else:
                    raw=doc['response']
                    if url.path!='/v1/markets/'+rule['slug']+'/settlement' or raw.get('slug')!=rule['slug']:raise ValueError('Weather settlement identity mismatch')
                    payout=number(raw['settlement'])
                    if not 0<=payout<=1:raise ValueError('Invalid settlement payout')
                    payouts[rule['slug']]=float(payout)
        if len(payouts)==len(rules) and abs(sum(payouts.values())-1)>1e-8:errors.append('Verified contract payouts do not form unit exclusive payout; possible cancellation or inconsistent settlement')
        row=rowmap.get((station,date));model=cal['models'].get(station)
        entry=dict(**group,target=target,histories=histories,payouts=payouts,row=row,model=model)
        groups.append(entry);coverage.append(dict(date=date,station=station,contracts=len(rules),price_records=sum(len(v) for v in histories.values()),settlements=len(payouts),errors=errors))
    results=[]
    period_start=min((g['target'] for g in groups),default=0)
    period_end=max(((datetime.fromisoformat(g['date'])+timedelta(days=1)).replace(hour=11,tzinfo=ZoneInfo('America/New_York')).timestamp() for g in groups),default=period_start)
    expense=200*max(0,period_end-period_start)/(30*86400)
    for slip in cfg['slippage_per_side']:
        for strategy in ['mos_calibrated','mos_uncorrected','market_baseline']:
            account=Account(cfg['capital'],cfg['reserve']);events=[];selected={};rejections=[];diagnostics=[]
            for g in groups:
                row,model=g['row'],g['model'];rules=g['rules'];target=g['target']
                if not row or not model:rejections.append(dict(date=g['date'],reason='No calibration/forecast pair'));continue
                bands=[dict(condition=r['market_id'],unit='F',lower=r['lower'],upper=r['upper']) for r in rules]
                adjusted=model if strategy!='mos_uncorrected' else {**model,'bias_f':0}
                prediction=predict(adjusted,row['gfs'],row['nam'],bands,target)
                probabilities={p['condition']:p['probability'] for p in prediction['probabilities']}
                if strategy=='market_baseline':
                    mids={}
                    for r in rules:
                        old=[p for p in g['histories'].get(r['slug'],[]) if p['t']<=target and target-p['t']<=cfg['max_quote_age_seconds']]
                        if old:mids[r['market_id']]=old[-1]['mid']
                    if len(mids)!=len(rules):rejections.append(dict(date=g['date'],reason='Incomplete market baseline'));continue
                    probabilities={k:v/sum(mids.values()) for k,v in mids.items()}
                candidate,reason=choose_entry(rules,probabilities,g['histories'],target,cfg['entry_delay_seconds'],cfg['max_quote_age_seconds'],cfg['entry_budget'],cfg['min_expected_dollars'],slip)
                diagnostics.append(dict(date=g['date'],prediction_mean_f=prediction['mean_f'],prediction_std_f=prediction['std_f'],probabilities=probabilities,candidate=candidate))
                if not candidate:rejections.append(dict(date=g['date'],reason=reason));continue
                slug=candidate['slug'];selected[slug]=candidate;events.append((candidate['entry_t'],1,slug,None))
                if slug in g['payouts']:
                    # Exact historical exchange settlement receipt time is not
                    # supplied. Use a separately disclosed conservative schedule.
                    release=(datetime.fromisoformat(g['date'])+timedelta(days=1)).replace(hour=11,tzinfo=ZoneInfo('America/New_York')).timestamp()
                    release=max(release,row['observation_issued_at'])
                    payout=g['payouts'][slug] if candidate['side']=='long' else 1-g['payouts'][slug]
                    events.append((release,0,slug,payout))
            curve=[]
            for t,is_entry,slug,payout in sorted(events):
                if is_entry:
                    o=selected[slug];p=number(o['price']);budget=min(number(cfg['entry_budget']),account.cash-account.reserve);q=int(budget/p)
                    while q and p*q+conservative_taker_fee(p,q)>budget:q-=1
                    if not q:rejections.append(dict(slug=slug,reason='Reserve or whole-contract size'));continue
                    if number(o['probability'])*q-p*q-conservative_taker_fee(p,q)<number(cfg['min_expected_dollars']):rejections.append(dict(slug=slug,reason='Expected edge below minimum after portfolio sizing'));continue
                    account.buy(slug,p,q,t);account.ledger[-1].update(side=o['side'],signal_t=o['signal_t'],probability=o['probability'])
                elif slug in account.positions:account.close(slug,payout,t,settlement=True)
                s=account.snapshot();curve.append(dict(t=t,realized_pnl=float(s['realized_pnl']),open_basis=float(s['open_basis']),cash=float(s['cash'])))
            s=account.snapshot()
            results.append(dict(**s,strategy=strategy,slippage_per_side=slip,entries=sum(x['kind']=='buy' for x in account.ledger),exits=sum(x['kind']=='settlement' for x in account.ledger),curve=curve,ledger=account.ledger,rejections=rejections,diagnostics=diagnostics,subscription_expense_prorated=expense,realized_after_subscription=float(s['realized_pnl'])-expense,fill_validated=False))
    report=dict(created_at=time.time(),venue='polymarket_us',period_start=period_start,period_end=period_end,history_directory=str(history_dir),calibration_directory=str(calibration_dir),registration=cfg,coverage=coverage,results=results,source_hashes=source_hashes,calibration_sha256=hashlib.sha256((calibration_dir/'report.json').read_bytes()).hexdigest(),code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),limitations=['Current .0695 fee schedule is a counterfactual cost scenario on earlier September prices.','MOS nominal runtime plus six hours is assumed availability, not proven original public receipt time.','Historical display prices lack fill depth, quote delivery times and matching fragmentation. Five-dollar notional capacity is assumed.','One city and six dates form a pilot, not statistical evidence of durable profitability.','Earliest complete archived CLI trains the model; final exchange payout is verified separately. Historical cash release at next-day 11 AM ET is a simulation timing assumption.','Unresolved positions stay open; do not interpret realized-only P&L without open basis.','No real orders or paper-account promotion.'],live_execution=False)
    output=history_dir/('replay-'+str(time.time_ns()));output.mkdir();(output/'report.json').write_text(json.dumps(report,indent=2));return output,report
