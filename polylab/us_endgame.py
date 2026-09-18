"""Costed near-settlement research; probability is a sensitivity, never inferred."""
from .us_accounting import number,conservative_taker_fee
from .us_http_age import response_age

def economics(price,depth,budget='5',slippage='0',depth_fraction='.25',probability=None,capital='50'):
    p=number(price)+number(slippage);d=number(depth);b=number(budget);f=number(depth_fraction);c=number(capital)
    if not 0<p<1 or d<0 or b<=0 or c<=0 or not 0<f<=1 or number(slippage)<0:raise ValueError('Invalid cost inputs')
    q=min(int(b/p),int(d*f))
    while q and q*p+conservative_taker_fee(p,q)>b:q-=1
    if not q:return dict(quantity=0,reason='Insufficient whole-contract depth or budget',expected_profit=None)
    fee=conservative_taker_fee(p,q);cost=q*p+fee;win=q-cost
    prob=None if probability is None else number(probability)
    if prob is not None and not 0<=prob<=1:raise ValueError('Invalid probability')
    return dict(quantity=q,price=str(p),fee=str(fee),cost=str(cost),conditional_win_profit=str(win),
        loss_if_wrong=str(-cost),conditional_position_return=str(win/cost),conditional_bankroll_return=str(win/c),
        break_even_probability=str(cost/q),probability_for_10pct_position_return=str(number('1.1')*cost/q),
        assumed_probability=None if prob is None else str(prob),expected_profit=None if prob is None else str(q*prob-cost),
        perfect_repeated_wins_to_exceed_5=int(number('5')/win)+1 if win>0 else None,
        note='Conditional payout or probability sensitivity only; no inferred fill, forecast accuracy, or realized profit.')

def screen(signal,book,receipt,cfg):
    if book['slug']!=signal['slug']:raise ValueError('Market identity mismatch')
    if not signal['observation_issued_at']<=signal['observation_available_at']<=receipt['requested_at']<=receipt['received_at']:raise ValueError('Information chronology')
    reasons=[];stamp=book.get('exchange_at');now=receipt['received_at']
    if not signal['complete_day']:reasons.append('CLI day incomplete: excluded from near-settlement arm')
    if book.get('state')!='MARKET_STATE_OPEN':reasons.append('Market not open')
    if stamp is None or not 0<=now-stamp<=cfg['max_exchange_age_seconds']:reasons.append('Exchange timestamp outside research gate')
    try:
        age=response_age(receipt,now)
        if not age['explicit_age'] or age['current_age_seconds']>cfg['max_http_age_seconds']:reasons.append('HTTP age incomplete or too old')
    except ValueError as exc:reasons.append(str(exc))
    if signal['side'] not in ['long','short']:raise ValueError('Unknown side')
    bids,asks=book['bids'],book['offers']
    if bids and asks and number(bids[0][0])>=number(asks[0][0]):reasons.append('Crossed or locked book')
    levels=asks if signal['side']=='long' else bids
    calc=None
    if not levels:reasons.append('Required side has no liquidity')
    else:
        p=number(levels[0][0]) if signal['side']=='long' else 1-number(levels[0][0])
        try:calc=economics(p,levels[0][1],cfg['entry_budget'],cfg['slippage_per_side'],cfg['depth_fraction'])
        except ValueError as exc:reasons.append(str(exc))
        if calc is not None and not calc['quantity']:reasons.append(calc['reason'])
        if calc and calc['quantity'] and number(calc['conditional_win_profit'])<number(cfg['minimum_conditional_margin']):reasons.append('Conditional gain below study threshold')
    return dict(signal=signal,reasons=reasons,economics=calc,research_qualified=not reasons,
        probability=None,expected_profit=None,realized_profit=None,positions_opened=0,execution_eligible=False,
        note='Only the required side needs displayed depth. This is a screen, not a fill simulation; corrections and settlement delay remain unpriced.')
