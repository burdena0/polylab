"""Ensemble temperature research with explicit settlement and availability contracts."""
import hashlib,json,math,re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import numpy as np
from .public_inputs import stations_from_rules
from .fees import validate as validate_fee,fee_usdc,unit_cost
from .probability import fractional_kelly

STRATEGIES={'ensemble-spread-probability-trading','weather-event-markets'}
STATION_ZONES={'KLGA':'America/New_York','KDAL':'America/Chicago','EGLC':'Europe/London','LFPB':'Europe/Paris','EHAM':'Europe/Amsterdam','EPWA':'Europe/Warsaw','LIMC':'Europe/Rome','FACT':'Africa/Johannesburg'}

def finite(value):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Expected finite numeric input')
    return value

def parse_rule(market):
    text=market.get('description','');ids=stations_from_rules(text)
    if len(ids)!=1 or 'recorded by NOAA' not in text:raise ValueError('Unsupported or ambiguous settlement source')
    station=next(iter(ids));date=re.search(r"on (\d{1,2} [A-Za-z]{3} '\d{2})",text)
    metric='max' if 'highest temperature recorded' in text else 'min' if 'lowest temperature recorded' in text else None
    unit='F' if 'whole degrees Fahrenheit' in text else 'C' if 'whole degrees Celsius' in text else None
    if not date or not metric or not unit:raise ValueError('Unrecognized date, metric, or precision')
    # These are extracted terms, not a claim that a source display's timezone and
    # numerical rounding behavior have been established by the prose.
    return dict(station=station,date=datetime.strptime(date.group(1),"%d %b '%y").date().isoformat(),metric=metric,unit=unit,precision=1,sampling='hourly' if 'Show Hourly Data' in text else 'all_readings',timezone=STATION_ZONES.get(station),timezone_verified=False,rounding='nearest_half_up',rounding_verified=False,revision_cutoff='first_next_day_datapoint' if 'after which any alterations will not be considered' in text else None,fallback='wunderground_then_lowest_bucket' if 'Weather Underground Daily Observations' in text and 'lowest bracket' in text else None,rule_sha256=hashlib.sha256(text.encode()).hexdigest(),source=market.get('resolutionSource'),condition=market['conditionId'])

def parse_band(market):
    text=market['groupItemTitle'].replace('\u00c2','').strip()
    match=re.fullmatch(r'(-?\d+)(?:\s*[-–]\s*(-?\d+))?°([CF])(?: (or below|or higher))?',text)
    if not match:raise ValueError('Unsupported temperature band')
    lo=int(match[1]);hi=int(match[2]) if match[2] else lo
    if lo>hi or (match[2] and match[4]):raise ValueError('Invalid band endpoints')
    return dict(condition=market['conditionId'],label=text,unit=match[3],lower=None if match[4]=='or below' else lo,upper=None if match[4]=='or higher' else hi)

def partition(bands):
    if not 2<=len(bands)<=100 or len({b['condition'] for b in bands})!=len(bands) or len({b['unit'] for b in bands})!=1:raise ValueError('Invalid partition identity or units')
    ordered=sorted(bands,key=lambda b:-math.inf if b['lower'] is None else b['lower'])
    if ordered[0]['lower'] is not None or ordered[-1]['upper'] is not None:raise ValueError('Missing outer tails')
    for i,b in enumerate(ordered):
        for key in ['lower','upper']:
            if b[key] is not None and (type(b[key]) is not int):raise ValueError('Integer settlement endpoints required')
        if b['lower'] is None and i!=0 or b['upper'] is None and i!=len(ordered)-1:raise ValueError('Overlapping outer tail')
        if b['lower'] is not None and b['upper'] is not None and b['lower']>b['upper']:raise ValueError('Reversed band')
    for a,b in zip(ordered,ordered[1:]):
        if a['upper']+1!=b['lower']:raise ValueError('Gapped or overlapping partition')
    return ordered

def daily_members(forecast,rule,available_at,asof):
    if finite(available_at)>finite(asof):raise ValueError('Forecast was not yet available')
    if rule['timezone'] is None:raise ValueError('Timezone unresolved')
    zone=ZoneInfo(rule['timezone']);start=datetime.fromisoformat(rule['date']).replace(tzinfo=zone);end=start+timedelta(days=1)
    begin=start.timestamp();finish=end.timestamp();hourly=forecast['hourly'];times=hourly['time']
    if forecast.get('utc_offset_seconds')!=0:raise ValueError('UTC ensemble input required')
    stamps=[datetime.fromisoformat(t).replace(tzinfo=timezone.utc).timestamp() for t in times]
    if len(stamps)!=len(set(stamps)) or stamps!=sorted(stamps):raise ValueError('Duplicate or unsorted forecast hours')
    indices=[i for i,t in enumerate(stamps) if begin<=t<finish]
    expected=list(np.arange(begin,finish,3600))
    if [stamps[i] for i in indices]!=expected:raise ValueError('Incomplete local calendar day')
    keys=sorted(k for k in hourly if re.fullmatch(r'temperature_2m(?:_member\d+)?',k))
    if len(keys)<20:raise ValueError('Full ensemble required, not a deterministic headline')
    result=[]
    for key in keys:
        if not forecast['hourly_units'][key].endswith('C') or len(hourly[key])!=len(stamps):raise ValueError('Unit or member shape mismatch')
        values=[finite(hourly[key][i]) for i in indices]
        if not all(-100<=x<=70 for x in values):raise ValueError('Invalid forecast temperature')
        result.append(max(values) if rule['metric']=='max' else min(values))
    return dict(values_c=result,members=len(result),hours=len(indices),available_at=available_at,day_start=begin,day_end=finish)

def fit_bias(rows,station,metric,model,asof):
    if len(rows)<20:raise ValueError('At least 20 distinct resolved station days required')
    dates=set();errors=[];spreads=[]
    for r in rows:
        if (r['station'],r['metric'],r['model'])!=(station,metric,model) or not r.get('resolution_verified'):raise ValueError('Calibration source identity unresolved')
        if r['date'] in dates:raise ValueError('Duplicate calibration day')
        dates.add(r['date'])
        if not finite(r['forecast_available_at'])<finite(r['day_start'])<finite(r['day_end'])<=finite(r['observed_available_at'])<=finite(asof):raise ValueError('Calibration lookahead')
        values=np.array([finite(v) for v in r['members_c']])
        if len(values)<20:raise ValueError('Incomplete calibration ensemble')
        errors.append(finite(r['observed_c'])-float(values.mean()));spreads.append(float(values.var()))
    bias=float(np.mean(errors));residual=np.array(errors)-bias
    factor=max(.25,min(5.,math.sqrt(float(np.mean(residual**2))/max(float(np.mean(spreads)),.01))))
    return dict(station=station,metric=metric,model=model,asof=asof,bias_c=bias,spread_factor=factor,samples=len(rows),residual_rmse_c=float(np.sqrt(np.mean(residual**2))),source_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest())

def distribution(members,rule,bands,bias=None,model=None,asof=None,observed=None):
    bands=partition(bands)
    if bands[0]['unit']!=rule['unit']:raise ValueError('Forecast/band unit mismatch')
    values=np.array([finite(v) for v in members['values_c']]);blockers=[]
    if len(values)<20 or not np.all((-100<=values)&(values<=70)):raise ValueError('Invalid ensemble')
    if finite(members['available_at'])>finite(asof):raise ValueError('Future forecast')
    if bias:
        if (bias['station'],bias['metric'],bias['model'])!=(rule['station'],rule['metric'],model) or finite(bias['asof'])>asof or bias['samples']<20:raise ValueError('Invalid or future station calibration')
        values=values.mean()+finite(bias['bias_c'])+(values-values.mean())*finite(bias['spread_factor'])
    else:blockers.append('No held-out station bias/spread calibration')
    if not rule.get('timezone_verified'):blockers.append('Settlement timezone needs source verification')
    if not rule.get('rounding_verified'):blockers.append('Settlement rounding needs source verification')
    if rule.get('rounding')!='nearest_half_up':raise ValueError('Unsupported rounding convention')
    if observed is not None:
        if observed.get('station')!=rule['station'] or observed.get('date')!=rule['date'] or observed.get('sampling')!=rule['sampling'] or not observed.get('source_verified'):raise ValueError('Observation is not verified against the contract')
        if not finite(observed['observed_at'])<=finite(observed['available_at'])<=asof:raise ValueError('Future observation')
        peak=finite(observed['extreme_c']);values=np.maximum(values,peak) if rule['metric']=='max' else np.minimum(values,peak)
    elif members['day_start']<asof:blockers.append('In-day forecast lacks verified observed extreme')
    native=values*1.8+32 if rule['unit']=='F' else values
    rounded=np.floor(native+.5)  # explicit research convention, including negative values
    probabilities=[]
    for b in bands:
        hits=((rounded>=b['lower']) if b['lower'] is not None else np.ones(len(values),dtype=bool))&((rounded<=b['upper']) if b['upper'] is not None else np.ones(len(values),dtype=bool))
        probabilities.append(dict(**b,probability=float(hits.mean()),member_count=int(hits.sum())))
    if abs(sum(r['probability'] for r in probabilities)-1)>1e-10:raise ValueError('Probability mass lost')
    return dict(model=model,station=rule['station'],date=rule['date'],metric=rule['metric'],members=len(values),mean_c=float(values.mean()),spread_c=float(values.std()),probabilities=probabilities,blockers=blockers,calibrated=bias is not None,execution_eligible=False,note='Member frequency is an ensemble estimate, not a binomial confidence interval: members are correlated. Grid forecasts and hourly interpolation are not station truth.')

def candidates(result,quotes,asof,capital=50.,exposure=.15,kelly=.1):
    if not 0<capital<=100000 or not 0<exposure<=.2 or not 0<kelly<=.25:raise ValueError('Invalid research budget')
    if len({q['condition'] for q in quotes})!=len(quotes):raise ValueError('Duplicate quote conditions')
    mapping={p['condition']:p for p in result['probabilities']};rows=[]
    for q in quotes:
        if q['condition'] not in mapping:raise ValueError('Quote identity not in probability partition')
        schedule=validate_fee(q['fee_schedule'],q['condition'],asof)
        if not 0<=asof-finite(q['exchange_at'])<=5 or not 0<=asof-finite(q['received_at'])<=5:raise ValueError('Stale candidate book')
        p=mapping[q['condition']]['probability']
        for side,prob in [('yes',p),('no',1-p)]:
            book=q[side];bid=finite(book['bid']);ask=finite(book['ask']);depth=finite(book['ask_size'])
            if not 0<bid<ask<1 or depth<=0:raise ValueError('Invalid candidate book')
            price=ask+.001
            if price>=1:continue
            all_in=unit_cost(price,schedule);budget=min(capital*exposure,fractional_kelly(capital,prob,all_in,kelly));quantity=min(max(0,budget-.00001)/all_in,depth*.25);cost=quantity*price+fee_usdc(quantity,price,schedule);ev=quantity*prob-cost
            rows.append(dict(condition=q['condition'],side=side,probability=prob,ask=ask,quantity=quantity,cost=cost,expected_net_pnl=ev,above_minimum=quantity>=q['minimum_shares'] and cost>=1,blockers=result['blockers'],execution_eligible=False))
    return sorted(rows,key=lambda r:r['expected_net_pnl'],reverse=True)
