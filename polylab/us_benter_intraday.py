"""Benter combination with station nowcasts; chronologically separated fitting."""
import bisect,json,time,hashlib
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from .us_accounting import number,conservative_taker_fee as fee
from .us_allocation import cents
from .us_multiband import frontier,pack_city,select
from .us_benter import vector,combine,fit_combination,exclusive_outcome
from .us_mos import predict as predict_mos
from .us_replay import normalize_history

def options(group,cfg,slip,method):
    if group['model_asof']>=group['target']:raise ValueError('Future combination model')
    probabilities=group['probabilities'][method];by_contract={}
    for rule,p in zip(group['rules'],probabilities):
        points=group['histories'][rule['slug']];index=bisect.bisect_right([q['t'] for q in points],group['target'])-1
        if index<0 or group['target']-points[index]['t']>cfg['max_quote_age_seconds']:return [],'Incomplete contemporaneous ladder'
        quote=points[index];choices=[]
        for side,prob,raw in [('long',p,number(quote['ask'])),('short',1-p,1-number(quote['bid']))]:
            price=raw+number(slip)
            if not 0<price<1:continue
            for q in range(1,int(number(cfg['entry_budget'])/price)+1):
                cost=q*price+fee(price,q)
                if cost>number(cfg['entry_budget']):break
                ev=number(prob)*q-cost
                if ev<number(cfg['min_expected_dollars']):continue
                choices.append(dict(station=group['station'],date=group['date'],slug=rule['slug'],side=side,quantity=q,probability=prob,expected=str(ev),cost_cents=cents(cost),signal_price=str(price),signal_t=group['target']))
        by_contract[rule['slug']]=frontier(choices)
    packs=pack_city(by_contract,cents(cfg['entry_budget']))
    return packs,None if packs else 'No positive expected dollars after costs'

def load(history,inputs,project):
    cfg=json.loads((history/'registration.json').read_text());forecast=json.loads((inputs/'report.json').read_text());groups=[];coverage=[];hashes={}
    original=json.loads((project/cfg['forecast_rows']).read_text())['rows'];rowmap={(r['station'],r['date']):r for r in original}
    preds={(r['station'],r['date']):r for r in forecast['predictions']}
    for g in cfg['groups']:
        histories={};payouts={};reasons=[]
        for rule in g['rules']:
            for kind in ['history','settlement']:
                path=history/(rule['market_id']+'-'+kind+'.json')
                if not path.exists():raise ValueError('Collection incomplete: '+path.name)
                hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest();doc=json.loads(path.read_text());url=urlparse(doc['receipt']['url'])
                if url.scheme!='https' or url.hostname!='gateway.polymarket.us':raise ValueError('Wrong source venue')
                if kind=='history':
                    if url.path!='/v1/price-history' or parse_qs(url.query).get('symbol')!=[rule['slug']]:raise ValueError('History identity')
                    histories[rule['slug']],_=normalize_history(doc['response'],g['target']-1800,g['target']+2700)
                else:
                    if url.path!='/v1/markets/'+rule['slug']+'/settlement' or doc['response'].get('slug')!=rule['slug']:raise ValueError('Settlement identity')
                    payouts[rule['slug']]=float(number(doc['response']['settlement']))
        key=(g['station'],g['date']);pred=preds.get(key);row=rowmap.get(key)
        if pred is None or row is None:reasons.append('Missing common forecast input')
        if pred and pred['target']!=g['target']:raise ValueError('Forecast target mismatch')
        mids=[]
        for rule in g['rules']:
            points=histories[rule['slug']];i=bisect.bisect_right([p['t'] for p in points],g['target'])-1
            if i<0 or g['target']-points[i]['t']>cfg['max_quote_age_seconds']:reasons.append('Incomplete signal ladder');break
            mids.append(points[i]['mid'])
        outcome=exclusive_outcome(payouts,g['rules'])
        if outcome is None:reasons.append('No unique binary settlement; uncertain release excluded')
        coverage.append(dict(station=g['station'],date=g['date'],role=g['role'],reasons=sorted(set(reasons))))
        if reasons:continue
        baseline=forecast['baseline_models'][g['station']];mos=predict_mos(baseline,row['gfs'],row['nam'],g['rules'],g['target'])
        release=max((datetime.fromisoformat(g['date'])+timedelta(days=1)).replace(hour=11,tzinfo=ZoneInfo('America/New_York')).timestamp(),row['observation_issued_at'])
        groups.append(dict(**g,histories=histories,payouts=payouts,release=release,label_available_at=release,outcome=outcome,market=vector(mids).tolist(),nowcast=pred['probabilities'],mos=[p['probability'] for p in mos['probabilities']]))
    calibration=[g for g in groups if g['role']=='calibration'];asof=max((g['label_available_at'] for g in calibration),default=0)+1;models={}
    for name in ['nowcast','mos']:
        rows=[dict(station=g['station'],date=g['date'],role='calibration',target=g['target'],label_available_at=g['label_available_at'],outcome=g['outcome'],fundamental=g[name],market=g['market']) for g in calibration]
        models[name]=fit_combination(rows,cfg,asof)
    tests=[g for g in groups if g['role']=='test']
    for g in tests:
        if asof>=g['target']:raise ValueError('Combination lookahead')
        g['model_asof']=asof;g['probabilities']=dict(market_only=g['market'],nowcast_only=g['nowcast'],benter_nowcast=combine(g['nowcast'],g['market'],[models['nowcast']['alpha'],models['nowcast']['beta']]),benter_mos=combine(g['mos'],g['market'],[models['mos']['alpha'],models['mos']['beta']]))
    return cfg,tests,models,coverage,hashes
