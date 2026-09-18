"""Expected-dollar allocation across multiple bands; no orders or new forecast."""
import bisect
from decimal import ROUND_FLOOR
from .us_allocation import cents,select as choose_cities
from .us_accounting import number,conservative_taker_fee as fee

def frontier(options):
    result=[];best=number('-1')
    for o in sorted(options,key=lambda o:(o['cost_cents'],-number(o['expected']),str(o.get('legs',o.get('slug',''))))):
        if number(o['expected'])>best:result.append(o);best=number(o['expected'])
    return result

def pack_city(by_contract,limit_cents):
    """At most one side/quantity choice per instrument; bounded city spend."""
    states={0:(number(0),[])}
    for slug in sorted(by_contract):
        updated=dict(states)
        for cost,(value,legs) in states.items():
            for o in by_contract[slug]:
                total=cost+o['cost_cents'];ev=value+number(o['expected'])
                if total<=limit_cents and (total not in updated or ev>updated[total][0]):updated[total]=(ev,legs+[o])
        states={};best=number('-1')
        for cost in sorted(updated):
            if updated[cost][0]>best:states[cost]=updated[cost];best=updated[cost][0]
    return [dict(cost_cents=cost,expected=str(ev),legs=legs) for cost,(ev,legs) in states.items() if legs]

def signal_options(group,cfg,slip):
    quotes=[]
    if cfg['model_asof']>=group['target']:raise ValueError('Future model')
    if len({r['slug'] for r in group['rules']})!=len(group['rules']):raise ValueError('Duplicate instruments')
    for rule in group['rules']:
        points=group['histories'].get(rule['slug'],[]);i=bisect.bisect_right([p['t'] for p in points],group['target'])-1
        if i<0 or group['target']-points[i]['t']>cfg['max_quote_age_seconds']:return [],'Incomplete contemporaneous ladder'
        quotes.append(points[i])
    weights=[max(p['mid'],1e-6)**cfg['beta'] for p in quotes];total=sum(weights);by_contract={}
    for rule,quote,weight in zip(group['rules'],quotes,weights):
        options=[];probability=weight/total
        for side,p,raw in [('long',probability,number(quote['ask'])),('short',1-probability,1-number(quote['bid']))]:
            price=raw+number(slip)
            if not 0<price<1:continue
            for q in range(1,int(number(cfg['entry_budget'])/price)+1):
                cost=price*q+fee(price,q)
                if cost>number(cfg['entry_budget']):break
                ev=number(p)*q-cost
                if ev<number(cfg['min_expected_dollars']):continue
                options.append(dict(station=group['station'],date=group['date'],slug=rule['slug'],side=side,quantity=q,probability=p,expected=str(ev),cost_cents=cents(cost),signal_price=str(price),signal_t=group['target']))
        by_contract[rule['slug']]=frontier(options)
    packs=pack_city(by_contract,cents(cfg['entry_budget'],ROUND_FLOOR))
    return packs,None if packs else 'No positive expected dollars after costs'

def select(options_by_city,available,method):
    if method!='multi_band':raise ValueError('Unknown multi-band method')
    packs=choose_cities(options_by_city,available,'expected_dollars')
    return [leg for pack in packs for leg in pack['legs']]

def event_payoffs(legs,rules):
    """Mutually exclusive settlement states, not independent coin flips."""
    ordered=sorted(rules,key=lambda r:float('-inf') if r['lower'] is None else r['lower'])
    if not ordered or ordered[0]['lower'] is not None or ordered[-1]['upper'] is not None:raise ValueError('Missing event tails')
    for a,b in zip(ordered,ordered[1:]):
        if a['upper'] is None or b['lower'] is None or a['upper']+1!=b['lower']:raise ValueError('Bands overlap or leave a gap')
    if len({r['slug'] for r in ordered})!=len(ordered):raise ValueError('Duplicate band')
    ids={r['slug'] for r in ordered}
    if any(l['slug'] not in ids or l['side'] not in ['long','short'] for l in legs):raise ValueError('Unknown leg')
    cost=sum((number(l['signal_price'])*l['quantity']+fee(l['signal_price'],l['quantity']) for l in legs),number(0))
    return [dict(winner=r['slug'],pnl=str(sum((number(l['quantity'])*int((l['slug']==r['slug'])==(l['side']=='long')) for l in legs),number(0))-cost)) for r in ordered]
