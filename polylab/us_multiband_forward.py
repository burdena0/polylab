"""Forward quote-paper helpers. Required depth is observed; fills remain assumed."""
from .us_accounting import Account,number,conservative_taker_fee as fee
from .us_http_age import response_age
from .us_multiband import signal_options as multi_options,select as multi_select
from .us_allocation import signal_options as single_options,select as single_select

def usable(book,receipt,asof,cfg):
    reasons=[]
    if not receipt['requested_at']<=receipt['received_at']<=asof:reasons.append('Receipt chronology')
    if not book.get('valid') or book.get('state')!='MARKET_STATE_OPEN':reasons.append('Not an open two-sided book')
    try:
        age=response_age(receipt,asof)
        if not age['explicit_age'] or age['current_age_seconds']>cfg['max_http_age_seconds']:reasons.append('HTTP age outside protocol')
    except ValueError as exc:reasons.append(str(exc))
    if book.get('exchange_at') is None or book['exchange_at']>receipt['received_at']+5:reasons.append('Missing or future exchange timestamp')
    return reasons

def plan(groups,cfg,signal_books):
    arms=[];rejections=[]
    for method in ['single_band','multi_band']:
        opts={}
        for g in groups:
            histories={};reasons=[]
            for r in g['rules']:
                raw=signal_books.get(r['slug'])
                if raw is None:reasons.append('Missing signal book');continue
                if raw['book']['slug']!=r['slug']:raise ValueError('Signal instrument mismatch')
                bad=usable(raw['book'],raw['receipt'],cfg['target'],dict(cfg,max_http_age_seconds=cfg['max_signal_http_age_seconds']))
                if bad:reasons.extend(bad);continue
                b=raw['book'];bid,ask=b['bids'][0][0],b['offers'][0][0]
                histories[r['slug']]=[dict(t=raw['receipt']['received_at'],bid=bid,ask=ask,mid=(bid+ask)/2)]
            if reasons:rejections.append(dict(method=method,station=g['station'],reasons=sorted(set(reasons))));continue
            group=dict(**g,target=cfg['target'],histories=histories)
            choices,reason=(multi_options if method=='multi_band' else single_options)(group,cfg,cfg['slippage_per_side'])
            opts[g['station']]=choices
            if reason:rejections.append(dict(method=method,station=g['station'],reasons=[reason]))
        chosen=multi_select(opts,number(cfg['capital'])-number(cfg['reserve']),method) if method=='multi_band' else single_select(opts,number(cfg['capital'])-number(cfg['reserve']),'expected_dollars')
        arms.append(dict(method=method,selected=chosen))
    return dict(target=cfg['target'],arms=arms,rejections=rejections,live_execution=False)

def evaluate(planned,entry_books,settlements,cfg):
    results=[]
    for arm in planned['arms']:
        account=Account(cfg['capital'],cfg['reserve']);rejections=[]
        for o in sorted(arm['selected'],key=lambda o:(entry_books.get(o['slug'],{}).get('receipt',{}).get('received_at',float('inf')),o['slug'])):
            raw=entry_books.get(o['slug'])
            if raw is None:rejections.append(dict(slug=o['slug'],reasons=['Missing delayed quote']));continue
            receipt=raw['receipt'];book=raw['book']
            if book['slug']!=o['slug']:raise ValueError('Entry instrument mismatch')
            bad=usable(book,receipt,receipt['received_at'],cfg)
            if not cfg['target']+cfg['entry_delay_seconds']<=receipt['requested_at']<=receipt['received_at']<=cfg['entry_deadline']:bad.append('Outside delayed entry window')
            if bad:rejections.append(dict(slug=o['slug'],reasons=bad));continue
            level=book['offers'][0] if o['side']=='long' else book['bids'][0]
            price=(number(level[0]) if o['side']=='long' else 1-number(level[0]))+number(cfg['slippage_per_side'])
            if not 0<price<1:rejections.append(dict(slug=o['slug'],reasons=['Invalid stressed price']));continue
            q=min(o['quantity'],int(number(level[1])*number(cfg['depth_fraction'])))
            budget=min(number(o['cost_cents'])/100,account.cash-account.reserve)
            while q and q*price+fee(price,q)>budget:q-=1
            ev=number(o['probability'])*q-price*q-fee(price,q) if q else number(0)
            if not q or ev<number(cfg['min_expected_dollars']):rejections.append(dict(slug=o['slug'],reasons=['Depth, budget or delayed edge failed']));continue
            account.buy(o['slug'],price,q,receipt['received_at'])
            account.ledger[-1].update(side=o['side'],station=o['station'],probability=o['probability'],expected_dollars=str(ev),observed_depth=level[1],planned_quantity=o['quantity'])
        for row in sorted(settlements.values(),key=lambda s:s['receipt']['received_at']):
            slug=row['response'].get('slug')
            if slug not in account.positions:continue
            t=row['receipt']['received_at']
            if row['receipt']['requested_at']<cfg['settlement_not_before']:raise ValueError('Settlement requested before registered release')
            p=number(row['response']['settlement'])
            side=next(o['side'] for o in arm['selected'] if o['slug']==slug)
            account.close(slug,p if side=='long' else 1-p,t,settlement=True)
        results.append(dict(method=arm['method'],**account.snapshot(),ledger=account.ledger,rejections=rejections,fill_validated=False))
    return dict(results=results,monthly_subscription=0,live_execution=False,note='Forward quote-paper: receipt and displayed depth verified; queue position, intervening depth and actual fills unverified.')
