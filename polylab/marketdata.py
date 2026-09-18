"""Fixed public endpoints only. No authentication, wallets, or order methods."""
import json,time,math
import requests
from .fees import observed_schedule
GAMMA='https://gamma-api.polymarket.com'
CLOB='https://clob.polymarket.com'

def get(url,params=None):
    r=requests.get(url,params=params,timeout=8);r.raise_for_status()
    if len(r.content)>8_000_000:raise ValueError('Public response too large')
    return r.json()

def array(v):return json.loads(v) if isinstance(v,str) else v

def btc_market(interval=300):
    now=time.time();start=int(now//interval)*interval
    slug=f'btc-updown-{interval//60}m-{start}'
    values=get(GAMMA+'/markets',{'slug':slug})
    for m in values:
        if m.get('slug')!=slug or m.get('closed') or not m.get('acceptingOrders'):continue
        outcomes=array(m['outcomes']);tokens=array(m['clobTokenIds']);mapping=dict(zip([o.lower() for o in outcomes],tokens))
        if set(mapping)!={'up','down'}:continue
        return dict(condition=m['conditionId'],up=mapping['up'],down=mapping['down'],start=start,end=start+interval,question=m['question'],slug=slug,min_shares=float(m.get('orderMinSize',5)),fee_schedule=observed_schedule(m,time.time()))
    return None

def book(token):
    received=time.time();r=get(CLOB+'/book',{'token_id':token});received=time.time()
    if str(r.get('asset_id'))!=str(token):raise ValueError('Token mismatch')
    def levels(name):
        result=[]
        for item in r.get(name,[]):
            p=float(item['price']);s=float(item['size'])
            if not math.isfinite(p+s) or not 0<p<1 or s<=0:raise ValueError('Invalid depth')
            result.append((p,s))
        return sorted(result,reverse=name=='bids')
    bids=levels('bids');asks=levels('asks');timestamp=float(r['timestamp'])/1000
    if not bids or not asks or bids[0][0]>=asks[0][0]:raise ValueError('Empty or crossed book')
    return dict(condition=r['market'],token=token,bids=bids,asks=asks,exchange_at=timestamp,received_at=received,age=received-timestamp,min_shares=float(r.get('min_order_size',5)))

def btc_tick(m):
    u=book(m['up']);d=book(m['down'])
    if u['condition']!=m['condition'] or d['condition']!=m['condition']:raise ValueError('Condition mismatch')
    if not all(0<=b['age']<=5 for b in [u,d]) or abs(u['received_at']-d['received_at'])>3:raise ValueError('Stale or asynchronous books')
    return dict(t=time.time(),bu=u['bids'][0][0],au=u['asks'][0][0],bd=d['bids'][0][0],ad=d['asks'][0][0],su=u['bids'][0][1],sau=u['asks'][0][1],sd=d['bids'][0][1],sad=d['asks'][0][1],up_exchange=u['exchange_at'],down_exchange=d['exchange_at'])

def weather_markets(limit=128):
    tag=get(GAMMA+'/tags/slug/weather')['id'];events=get(GAMMA+'/events',{'tag_id':tag,'closed':'false','limit':100})
    selected=[]
    for e in events:
        title=e.get('title','')
        if not any(term in title.lower() for term in ['highest temperature','lowest temperature']):continue
        city=title.split(' in ',1)[-1].split(' on ',1)[0]
        usa={'New York City','New York','NYC','Chicago','Los Angeles','Miami','Dallas','Atlanta','Seattle','Boston','Denver','Austin','San Francisco'}
        europe={'London','Paris','Berlin','Madrid','Rome','Munich','Warsaw','Amsterdam'}
        region='USA' if city in usa else 'Europe' if city in europe else 'Other regions'
        for m in e.get('markets',[]):
            if m.get('closed') or not m.get('acceptingOrders') or not m.get('enableOrderBook'):continue
            outcomes=array(m.get('outcomes',[]));tokens=array(m.get('clobTokenIds',[]))
            if len(tokens)!=len(outcomes) or not tokens:continue
            for token,outcome in zip(tokens,outcomes):
                selected.append(dict(token=token,outcome=outcome,condition=m['conditionId'],question=m['question'],city=city,region=region,date=m.get('endDate','')[:10],event=e['slug'],market_slug=m['slug'],min_shares=float(m.get('orderMinSize',5))))
    # Prefer complete city events, distributed across regions. Never claim complete coverage.
    groups={}
    for row in selected:groups.setdefault(row['event'],[]).append(row)
    regions={r:[] for r in ['USA','Europe','Other regions']}
    for rows in groups.values():regions[rows[0]['region']].append(rows)
    result=[]
    while any(regions.values()):
        for candidates in regions.values():
            if candidates:
                rows=candidates.pop(0)
                if len(result)+len(rows)<=limit:result.extend(rows)
    return result
