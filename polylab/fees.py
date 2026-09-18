"""Observed market fee schedules, never inferred from legacy base_fee fields."""
import math
from decimal import Decimal, ROUND_HALF_UP

SOURCE='https://docs.polymarket.com/trading/fees'

def number(value):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
        raise ValueError('Invalid fee numeric value')
    return value

def observed_schedule(market,received_at):
    enabled=market.get('feesEnabled');schedule=market.get('feeSchedule')
    if not market.get('conditionId') or type(enabled) is not bool:raise ValueError('Missing explicit fee metadata')
    if enabled:
        if not isinstance(schedule,dict):raise ValueError('Missing feeSchedule; legacy base fees are insufficient')
        rate=number(schedule.get('rate'));exponent=number(schedule.get('exponent'))
        if not 0<=rate<=1 or exponent!=1 or schedule.get('takerOnly') is not True:raise ValueError('Unsupported fee schedule')
    else:rate=0;exponent=1
    return dict(condition=market['conditionId'],received_at=number(received_at),enabled=enabled,rate=rate,exponent=exponent,taker_only=True,source='https://gamma-api.polymarket.com/markets',formula_source=SOURCE,raw_schedule=schedule)

def validate(schedule,condition,asof):
    if not isinstance(schedule,dict) or schedule.get('condition')!=condition:raise ValueError('Missing or mismatched fee receipt')
    age=number(asof)-number(schedule.get('received_at'))
    if not 0<=age<=920:raise ValueError('Fee receipt is stale or from the future')
    if schedule.get('exponent')!=1 or schedule.get('taker_only') is not True or not 0<=number(schedule.get('rate'))<=1:raise ValueError('Unsupported fee receipt')
    return schedule

def fee_usdc(shares,price,schedule,maker=False):
    q=number(shares);p=number(price);rate=number(schedule.get('rate'))
    if q<0 or not 0<=p<=1 or not 0<=rate<=1 or schedule.get('exponent')!=1 or schedule.get('taker_only') is not True:raise ValueError('Invalid fee calculation')
    if maker:return 0.
    value=Decimal(str(q))*Decimal(str(rate))*Decimal(str(p))*(1-Decimal(str(p)))
    return float(value.quantize(Decimal('0.00001'),rounding=ROUND_HALF_UP))

def unit_cost(price,schedule):
    return price+price*(1-price)*schedule['rate']
