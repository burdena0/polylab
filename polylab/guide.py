"""Guide's 15-minute BTC heuristic, using its documented Coinbase fallback.

This is an uncalibrated research signal, not a settlement probability estimate.
"""
from datetime import datetime,timezone
import time,math,re
from .marketdata import get

def guide_probability(up_mid,delta_percent):
    if not 0<up_mid<1 or not math.isfinite(delta_percent):raise ValueError('Invalid signal inputs')
    if abs(delta_percent)<=.10:return None
    p=max(.05,min(.95,up_mid+delta_percent*.10))
    if abs(p-up_mid)<.05:return None
    return p

def parse_timestamp(value):
    # Python 3.10 accepts microseconds; Coinbase can supply nanoseconds.
    value=re.sub(r'(\.\d{6})\d+',r'\1',value)
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()

def observe(up_mid):
    now=time.time();base='https://api.exchange.coinbase.com/products/BTC-USD'
    ticker=get(base+'/ticker');stamp=parse_timestamp(ticker['time'])
    if not 0<=now-stamp<=10:raise ValueError('Underlying BTC ticker is stale')
    candles=get(base+'/candles',{'granularity':60,'start':datetime.fromtimestamp(now-1140,timezone.utc).isoformat(),'end':datetime.fromtimestamp(now,timezone.utc).isoformat()})
    old=[c for c in candles if c[0]+60<=now-900]
    if not old:raise ValueError('Missing historical BTC reference')
    reference=max(old,key=lambda c:c[0]);price=float(ticker['price']);prior=float(reference[4])
    if prior<=0 or price<=0:raise ValueError('Invalid underlying price')
    delta=(price/prior-1)*100
    return dict(probability_up=guide_probability(up_mid,delta),delta_percent=delta,reference_at=reference[0]+60,observed_at=stamp,source='Coinbase public fallback; not Chainlink settlement oracle',calibrated=False)
