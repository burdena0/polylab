"""Registered US MOS/market probability combination; no order execution."""
import bisect,hashlib,json,time
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse,parse_qs
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from .us_mos import fit,predict
from .us_weather import window
from .us_replay import normalize_history
from .us_weather_replay import choose_entry
from .probability import odds_to_probabilities
from .us_accounting import Account,number,conservative_taker_fee

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def vector(values,floor=1e-6):
    p=np.asarray(values,dtype=float)
    if p.ndim!=1 or len(p)<2 or not np.isfinite(p).all() or (p<0).any() or (p>1).any() or p.sum()<=0:raise ValueError('Invalid probability vector')
    p=np.maximum(p,floor);return p/p.sum()

def combine(fundamental,market,weights,floor=1e-6):
    f,p=vector(fundamental,floor),vector(market,floor)
    if f.shape!=p.shape or len(weights)!=2 or not np.isfinite(weights).all():raise ValueError('Invalid combination inputs')
    z=weights[0]*np.log(f)+weights[1]*np.log(p)
    return np.exp(z-logsumexp(z)).tolist()

def fit_combination(rows,cfg,asof):
    if len(rows)<cfg['minimum_combination_dates'] or len({r['date'] for r in rows})!=len(rows):raise ValueError('Insufficient distinct calibration dates')
    start,end=cfg['combination_training'];training_end=cfg['forecast_training'][1]
    for r in rows:
        if r['role']!='calibration' or not training_end<start<=r['date']<=end or not r['target']<r['label_available_at']<asof:raise ValueError('Combination calibration chronology violated')
        if r['station']!=cfg['station']:raise ValueError('Combination station mismatch')
        if type(r['outcome']) is not int or not 0<=r['outcome']<len(r['fundamental']):raise ValueError('Invalid calibration outcome')
    floor=cfg['probability_floor'];f=[np.log(vector(r['fundamental'],floor)) for r in rows];p=[np.log(vector(r['market'],floor)) for r in rows]
    if any(a.shape!=b.shape for a,b in zip(f,p)):raise ValueError('Combination ladder mismatch')
    anchor=np.asarray(cfg['ridge_anchor']);penalty=cfg['ridge_penalty']
    def objective(w):
        loss=0.;grad=np.zeros(2)
        for a,b,r in zip(f,p,rows):
            z=w[0]*a+w[1]*b;probs=np.exp(z-logsumexp(z));y=r['outcome']
            loss+=logsumexp(z)-z[y];grad+=np.array([probs@a-a[y],probs@b-b[y]])
        return loss/len(rows)+penalty*np.square(w-anchor).sum(),grad/len(rows)+2*penalty*(w-anchor)
    result=minimize(objective,anchor,jac=True,bounds=[tuple(cfg['weight_bounds'])]*2,method='L-BFGS-B',options={'maxiter':400,'ftol':1e-12,'gtol':1e-8})
    if not result.success or not np.isfinite(result.fun):raise ValueError('Combination optimization failed')
    return dict(alpha=float(result.x[0]),beta=float(result.x[1]),asof=asof,calibration_dates=len(rows),dates=[r['date'] for r in rows],penalized_objective=float(result.fun),calibration_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),method='Bounded, ridge-regularized adaptation of Benter log-probability combination',availability_verified=False)

def signal_market(group,max_age):
    mids=[];asks=[]
    for r in group['rules']:
        points=group['histories'].get(r['slug'],[]);i=bisect.bisect_right([p['t'] for p in points],group['target'])-1
        if i<0 or group['target']-points[i]['t']>max_age:raise ValueError('Incomplete contemporaneous price ladder')
        mids.append(points[i]['mid']);asks.append(points[i]['ask'])
    return vector(mids).tolist(),asks

def exclusive_outcome(payouts,rules):
    if len(payouts)!=len(rules):return None
    values=[payouts[r['slug']] for r in rules]
    if any(x not in (0.,1.) for x in values) or sum(values)!=1:return None
    return values.index(1.)

def load_groups(root,cfg,forecast_rows,model):
    groups=[];coverage=[];hashes={};rowmap={(r['station'],r['date']):r for r in forecast_rows};seen=set()
    for g in cfg['groups']:
        rules=g['rules'];day=g['date'];role=g['role'];bounds=cfg['combination_training'] if role=='calibration' else cfg['test_dates']
        if role not in ('calibration','test') or not bounds[0]<=day<=bounds[1] or day in seen or any(r['date']!=day or r['station']!=cfg['station'] for r in rules):raise ValueError('Study group identity/role mismatch')
        seen.add(day);target=int(window(rules[0])[0]-cfg['decision_seconds_before_climate_day_start']);histories={};payouts={};errors=[]
        for r in rules:
            for kind in ('history','settlement'):
                path=root/(r['market_id']+'-'+kind+'.json')
                if not path.exists():errors.append(r['slug']+': missing '+kind);continue
                hashes[path.name]=digest(path);doc=json.loads(path.read_text());url=urlparse(doc['receipt']['url'])
                if url.scheme!='https' or url.hostname!='gateway.polymarket.us':raise ValueError('Wrong venue receipt')
                if kind=='history':
                    if url.path!='/v1/price-history' or parse_qs(url.query).get('symbol')!=[r['slug']]:raise ValueError('History identity mismatch')
                    points,rejected=normalize_history(doc['response'],target-1800,target+2700);histories[r['slug']]=points
                    if not points:errors.append(r['slug']+': no usable history')
                else:
                    if url.path!='/v1/markets/'+r['slug']+'/settlement' or doc['response'].get('slug')!=r['slug']:raise ValueError('Settlement identity mismatch')
                    p=number(doc['response']['settlement'])
                    if not 0<=p<=1:raise ValueError('Invalid payout')
                    payouts[r['slug']]=float(p)
        row=rowmap.get((cfg['station'],day));release=(datetime.fromisoformat(day)+timedelta(days=1)).replace(hour=11,tzinfo=ZoneInfo('America/New_York')).timestamp()
        if row:release=max(release,row['observation_issued_at'])
        entry=dict(**g,station=cfg['station'],target=target,histories=histories,payouts=payouts,release=release,label_available_at=release+86400,outcome=exclusive_outcome(payouts,rules))
        try:
            if not row:raise ValueError('No MOS/CLI pair')
            prediction=predict(model,row['gfs'],row['nam'],[dict(condition=r['market_id'],unit='F',lower=r['lower'],upper=r['upper']) for r in rules],target)
            by_id={p['condition']:p['probability'] for p in prediction['probabilities']}
            entry['fundamental']=vector([by_id[r['market_id']] for r in rules],cfg['probability_floor']).tolist()
            entry['market'],entry['asks']=signal_market(entry,cfg['max_quote_age_seconds'])
            entry['prediction']=prediction
        except ValueError as exc:errors.append(str(exc))
        groups.append(entry);coverage.append(dict(date=day,role=role,contracts=len(rules),price_records=sum(len(x) for x in histories.values()),settlements=len(payouts),complete_signal=all(k in entry for k in ('fundamental','market')),exclusive_outcome=entry['outcome'] is not None,errors=errors))
    return groups,coverage,hashes

def probabilities_for(group,strategy,model,cfg):
    if 'fundamental' not in group or 'market' not in group:raise ValueError('Incomplete forecast or contemporaneous market ladder')
    f,p=group['fundamental'],group['market']
    if strategy=='mos_only':return f
    if strategy=='market_only':return p
    if strategy=='fixed_blend':return combine(f,p,[.5,.5],cfg['probability_floor'])
    if strategy=='shin_asks':return odds_to_probabilities([1/a for a in group['asks']],'shin')['probabilities']
    if strategy!='benter':raise ValueError('Unknown strategy')
    if model is None:raise ValueError('No fitted combination: calibration coverage insufficient')
    if model['asof']>group['target']:raise ValueError('Combination model unavailable at decision')
    return combine(f,p,[model['alpha'],model['beta']],cfg['probability_floor'])

def simulate(groups,strategy,model,cfg,slippage):
    account=Account(cfg['capital'],cfg['reserve']);events=[];selected={};rejections=[];diagnostics=[];scores=[]
    if any(g['role']!='test' for g in groups):raise ValueError('Profit replay may only consume test groups')
    first=min(g['target'] for g in groups);end=max(g['release'] for g in groups)
    for g in groups:
        try:probs=probabilities_for(g,strategy,model,cfg)
        except ValueError as exc:rejections.append(dict(date=g['date'],reason=str(exc)));continue
        y=g['outcome']
        if y is not None:scores.append(dict(date=g['date'],log_loss=float(-np.log(max(probs[y],cfg['probability_floor']))),brier=float(sum((p-int(i==y))**2 for i,p in enumerate(probs))),outcome_probability=probs[y]))
        candidate,reason=choose_entry(g['rules'],dict(zip([r['market_id'] for r in g['rules']],probs)),g['histories'],g['target'],cfg['entry_delay_seconds'],cfg['max_quote_age_seconds'],cfg['entry_budget'],cfg['min_expected_dollars'],slippage)
        diagnostics.append(dict(date=g['date'],probabilities=probs,candidate=candidate))
        if not candidate:rejections.append(dict(date=g['date'],reason=reason));continue
        slug=candidate['slug'];selected[slug]=candidate;events.append((candidate['entry_t'],1,slug,None))
        if slug in g['payouts']:
            if g['release']<=candidate['entry_t']:raise ValueError('Settlement precedes entry')
            payout=g['payouts'][slug] if candidate['side']=='long' else 1-g['payouts'][slug]
            events.append((g['release'],0,slug,payout))
    curve=[]
    for t,is_entry,slug,payout in sorted(events):
        if is_entry:
            o=selected[slug];p=number(o['price']);budget=min(number(cfg['entry_budget']),account.cash-account.reserve);q=int(budget/p)
            while q and p*q+conservative_taker_fee(p,q)>budget:q-=1
            if not q:rejections.append(dict(slug=slug,reason='Reserve or whole-contract size'));continue
            if number(o['probability'])*q-p*q-conservative_taker_fee(p,q)<number(cfg['min_expected_dollars']):rejections.append(dict(slug=slug,reason='Expected edge below minimum after portfolio sizing'));continue
            account.buy(slug,p,q,t);account.ledger[-1].update(side=o['side'],signal_t=o['signal_t'],probability=o['probability'])
        elif slug in account.positions:account.close(slug,payout,t,settlement=True)
        snap=account.snapshot();curve.append(dict(t=t,realized_pnl=float(snap['realized_pnl']),cash=float(snap['cash']),open_basis=float(snap['open_basis'])))
    s=account.snapshot();expense=cfg['monthly_subscription']*(end-first)/(30*86400)
    return dict(**s,strategy=strategy,slippage_per_side=slippage,period_start=first,period_end=end,entries=sum(x['kind']=='buy' for x in account.ledger),exits=sum(x['kind']=='settlement' for x in account.ledger),curve=curve,ledger=account.ledger,rejections=rejections,diagnostics=diagnostics,probability_scores=scores,mean_log_loss=float(np.mean([r['log_loss'] for r in scores])) if scores else None,mean_brier=float(np.mean([r['brier'] for r in scores])) if scores else None,subscription_expense_prorated=expense,realized_after_subscription=float(s['realized_pnl'])-expense,fill_validated=False)

def run(directory,project_root):
    root=Path(directory);project_root=Path(project_root);cfg=json.loads((root/'registration.json').read_text())
    if json.loads((root/'collection.json').read_text())['status']!='complete':raise ValueError('Finish registered collection before evaluation')
    calpath=project_root/cfg['forecast_rows'];cal=json.loads(calpath.read_text());rows=cal['rows']
    training=[r for r in rows if r['station']==cfg['station'] and cfg['forecast_training'][0]<=r['date']<=cfg['forecast_training'][1]]
    forecast=fit(training,cfg['station'],max(r['observation_issued_at'] for r in training)+1)
    groups,coverage,hashes=load_groups(root,cfg,rows,forecast);test=[g for g in groups if g['role']=='test']
    if not test:raise ValueError('No registered test groups')
    calibrate=[{k:g[k] for k in ('date','role','station','target','label_available_at','outcome','fundamental','market')} for g in groups if g['role']=='calibration' and g['outcome'] is not None and 'fundamental' in g and 'market' in g]
    asof=max((g['label_available_at'] for g in calibrate),default=0)+1;model=None;fit_error=None
    if asof>=min(g['target'] for g in test):raise ValueError('Calibration labels overlap test decisions')
    try:model=fit_combination(calibrate,cfg,asof)
    except ValueError as exc:fit_error=str(exc)
    # Persist coefficients before opening any simulated test P&L result.
    dest=root/('analysis-'+str(time.time_ns()));dest.mkdir();(dest/'model.json').write_text(json.dumps(dict(forecast=forecast,combination=model,fit_error=fit_error,calibration=calibrate),indent=2))
    results=[simulate(test,strategy,model,cfg,slip) for slip in cfg['slippage_per_side'] for strategy in cfg['strategies']]
    report=dict(created_at=time.time(),venue='polymarket_us',registration=cfg,coverage=coverage,forecast_model=forecast,combination_model=model,fit_error=fit_error,eligible_calibration_dates=len(calibrate),results=results,source_hashes=hashes,forecast_rows_sha256=digest(calpath),registration_sha256=digest(root/'registration.json'),code_sha256={name:digest(project_root/name) for name in ['polylab/us_benter.py','polylab/us_mos.py','polylab/us_weather_replay.py','polylab/us_replay.py','polylab/us_accounting.py','polylab/probability.py']},limitations=['Exploratory US-only adaptation following a losing pilot; no selection or tuning based on this registered test P&L.','MOS publication assumed at runtime+6h; calibration labels use verified final payouts with assumed next-day 11AM ET release plus 24-hour fitting embargo, not verified historical publication receipts.','Current US fees are counterfactual on earlier prices; whole-contract historical fills and $5 capacity are unverified.','Shin is only an exchange-ask overround benchmark; bookmaker insider assumptions are not established for these markets.','Nine test dates from one city are too few to establish durable profit; lower log loss does not imply positive trading P&L.','Subscription expense is external to the $50 trading account and $40 reserve. No strategy is promoted into frozen forward paper trading.'],live_execution=False)
    (dest/'report.json').write_text(json.dumps(report,indent=2));return dest,report
