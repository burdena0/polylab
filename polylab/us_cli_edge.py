"""Prospective CLI information research. Conditional bounds are not forecasts."""
import math
from .us_weather import window
from .us_accounting import number, conservative_taker_fee
from .us_http_age import response_age

def latest_cli(observations, station, date, asof):
    valid=[o for o in observations if o['station']==station and o['date']==date and o['issued_at']<=o['available_at']<=asof]
    if not valid: return None
    issued=max(o['issued_at'] for o in valid)
    newest=[o for o in valid if o['issued_at']==issued]
    if len({(o['max_f'],o['min_f'],o['complete_day']) for o in newest})!=1:
        raise ValueError('Conflicting CLI versions with the same issuance time')
    return min(newest,key=lambda o:o['available_at'])

def conditional_direction(rule, observation, asof):
    if observation is None:return None
    if (rule['station'],rule['date'])!=(observation['station'],observation['date']):raise ValueError('Station/date mismatch')
    if not observation['issued_at']<=observation['available_at']<=asof:raise ValueError('Observation not yet available')
    if window(rule)[0]>asof:raise ValueError('Climate day has not started')
    value=observation['max_f'] if rule['metric']=='max' else observation['min_f']
    lo,hi=rule['lower'],rule['upper']
    if observation['complete_day']:
        inside=(lo is None or value>=lo) and (hi is None or value<=hi)
        side='long' if inside else 'short'
    elif rule['metric']=='max':
        side='short' if hi is not None and value>hi else ('long' if hi is None and (lo is None or value>=lo) else None)
    elif rule['metric']=='min':
        side='short' if lo is not None and value<lo else ('long' if lo is None and (hi is None or value<=hi) else None)
    else:raise ValueError('Unsupported metric')
    if side is None:return None
    return dict(slug=rule['slug'],station=rule['station'],date=rule['date'],side=side,observed_extreme_f=value,
                observation_available_at=observation['available_at'],observation_issued_at=observation['issued_at'],
                observation_sha256=observation['source_sha256'],complete_day=observation['complete_day'],
                assumption='CLI value is not corrected; complete-day value remains the exchange settlement reading',
                probability=None,expected_profit=None,execution_eligible=False)

def assess_quote(signal, book, receipt, cfg):
    asof=receipt['received_at'];reasons=[]
    if book['slug']!=signal['slug']:raise ValueError('Quote identity mismatch')
    if signal['observation_available_at']>receipt['requested_at']:raise ValueError('Quote requested before information receipt')
    try:age=response_age(receipt,asof)
    except ValueError as exc:age=None;reasons.append(str(exc))
    if age and (not age['explicit_age'] or age['current_age_seconds']>cfg['max_http_age_seconds']):reasons.append('HTTP age incomplete or outside research bound')
    stamp=book.get('exchange_at')
    fresh=stamp is not None and 0<=asof-stamp<=cfg['max_exchange_age_seconds']
    if not fresh:reasons.append('Exchange timestamp outside frozen freshness gate')
    if not book.get('valid') or book.get('state')!='MARKET_STATE_OPEN':reasons.append('No open two-sided book')
    result=dict(signal=signal,received_at=asof,book_exchange_at=stamp,http_age=age,reasons=reasons,quantity=0,
                conditional_margin=None,profit=None,positions_opened=0,live_execution=False)
    if not book.get('valid') or book.get('state')!='MARKET_STATE_OPEN':return result
    side=signal['side'];level=book['offers'][0] if side=='long' else book['bids'][0]
    price=(number(level[0]) if side=='long' else 1-number(level[0]))+number(cfg['slippage_per_side'])
    if not 0<price<1:result['reasons'].append('Invalid stressed price');return result
    q=min(int(number(cfg['entry_budget'])/price),int(number(level[1])*number(cfg['depth_fraction'])))
    while q and q*price+conservative_taker_fee(price,q)>number(cfg['entry_budget']):q-=1
    if not q:result['reasons'].append('Insufficient observed whole-contract depth');return result
    fee=conservative_taker_fee(price,q);margin=q-q*price-fee
    result.update(price=str(price),quantity=q,fee=str(fee),conditional_margin=str(margin),observed_depth=level[1],
                  observation_to_quote_seconds=asof-signal['observation_available_at'],
                  research_qualified=not reasons and margin>=number(cfg['minimum_conditional_margin']),
                  note='Margin assumes the CLI-derived side pays one dollar. No calibrated correction probability, fill or realized profit is established.')
    return result
