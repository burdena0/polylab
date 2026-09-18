"""US CLI contract rules and forecast distributions. No international venue API."""
import re,json,hashlib,math
from datetime import datetime,timedelta,timezone
from .weather_probability import partition,daily_members
from .us_accounting import number,conservative_taker_fee

# Official US weather FAQ station mapping; fixed LST per NWS 10-1004 and LOT FAQ.
STATIONS={'KNYC':dict(cli='NYC',offset=-5),'KSFO':dict(cli='SFO',offset=-8),'KMIA':dict(cli='MIA',offset=-5),'KMDW':dict(cli='MDW',offset=-6),'KLAX':dict(cli='LAX',offset=-8)}

def parse_contract(market):
    text=market.get('description','')
    match=re.fullmatch(r"Will the (highest|lowest) temperature recorded at .+ \((K[A-Z]{3})\) in .+ for (\d{4}-\d{2}-\d{2}) as reported by the National Weather Service's Climatological Report \(Daily\) be (.+)\? Outcome verified from NWS Climatological Report\.",text)
    if not match or match[2] not in STATIONS:raise ValueError('Unrecognized US CLI contract prose')
    metric='max' if match[1]=='highest' else 'min';station=match[2];date=match[3];term=match[4]
    datetime.fromisoformat(date)
    between=re.fullmatch(r'between (-?\d+)F and (-?\d+)F',term)
    tail=re.fullmatch(r'(less|greater) than or equal to (-?\d+)F',term)
    if between:lower,upper=int(between[1]),int(between[2])
    elif tail:lower,upper=(None,int(tail[2])) if tail[1]=='less' else (int(tail[2]),None)
    else:raise ValueError('Unsupported US temperature threshold')
    if lower is not None and upper is not None and lower>upper:raise ValueError('Reversed US temperature band')
    slug=market['slug'];identifier=str(market['id'])
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',slug) or not identifier.isdigit():raise ValueError('Invalid US identity')
    return dict(station=station,cli=STATIONS[station]['cli'],date=date,metric=metric,unit='F',timezone='Etc/GMT+'+str(-STATIONS[station]['offset']),standard_utc_offset=STATIONS[station]['offset'],market_id=identifier,slug=slug,condition=identifier,lower=lower,upper=upper,label=term,description_sha256=hashlib.sha256(text.encode()).hexdigest(),settlement_source='NWS CLI',settlement_note='8 AM ET next day; discrepancy review to 11 AM; one-week missing-data fallback is last fair market price',timezone_verified=True,execution_eligible=False)

def window(rule):
    start=datetime.fromisoformat(rule['date']).replace(tzinfo=timezone(timedelta(hours=rule['standard_utc_offset'])))
    return start.timestamp(),(start+timedelta(days=1)).timestamp()

def parse_cli(document,station,received_at):
    if station not in STATIONS or document.get('productCode')!='CLI':raise ValueError('Unsupported CLI source identity')
    text=document['productText'];code=STATIONS[station]['cli']
    if not re.search(r'^CLI'+code+r'\s*$',text,re.M):raise ValueError('CLI station does not match contract')
    dates=re.findall(r'CLIMATE SUMMARY FOR ([A-Z]+ \d{1,2} \d{4})',text)
    if len(dates)!=1:raise ValueError('Ambiguous CLI reporting date')
    date=datetime.strptime(dates[0],'%B %d %Y').date().isoformat()
    issued=datetime.fromisoformat(document['issuanceTime'].replace('Z','+00:00')).timestamp()
    if not math.isfinite(received_at) or issued>received_at:raise ValueError('CLI received before issuance')
    section=re.search(r'TEMPERATURE \(F\)(.*?)(?:PRECIPITATION|SNOWFALL|DEGREE DAYS)',text,re.S)
    if not section:raise ValueError('Missing CLI temperature table')
    values={}
    for label,key in [('MAXIMUM','max_f'),('MINIMUM','min_f')]:
        rows=re.findall(r'^\s*'+label+r'\s+(-?\d+|MM)(?:\s|R)',section[1],re.M)
        if len(rows)!=1 or rows[0]=='MM':raise ValueError('Missing or ambiguous CLI '+key)
        values[key]=int(rows[0])
    if not -150<=values['min_f']<=values['max_f']<=150:raise ValueError('Implausible CLI temperatures')
    _,end=window(dict(date=date,standard_utc_offset=STATIONS[station]['offset']))
    partial='VALID TODAY AS OF' in text or bool(re.search(r'^\s*TODAY\s*$',section[1],re.M))
    complete=issued>=end and not partial
    return dict(station=station,date=date,cli=code,**values,issued_at=issued,available_at=received_at,complete_day=complete,interim=not complete,product_id=document['id'],source_sha256=hashlib.sha256(text.encode()).hexdigest(),exchange_settlement_verified=False,note='CLI observation, not exchange settlement. Even a complete-day CLI may be revised.')

def probabilities(forecast,receipt,rule,bands,model,asof,cli=None):
    bands=partition(bands)
    if any(b['unit']!='F' for b in bands):raise ValueError('US Fahrenheit bands required')
    members=daily_members(forecast,rule,receipt['available_at'],asof)
    native=[v*1.8+32 for v in members['values_c']]
    rounded=[math.floor(v+.5) for v in native]
    blockers=['No held-out station/model calibration','Hourly grid extremes differ from station continuous observations','Nearest-degree quantization is a model assumption; learn CLI error empirically']
    if cli:
        if cli['station']!=rule['station'] or cli['date']!=rule['date'] or not cli['issued_at']<=cli['available_at']<=asof:raise ValueError('CLI date or availability mismatch')
        value=cli['max_f'] if rule['metric']=='max' else cli['min_f']
        # CLI values already have Fahrenheit integer precision. Do not treat
        # their displayed center as an exact unrounded Celsius observation.
        rounded=[max(v,value) if rule['metric']=='max' else min(v,value) for v in rounded]
        blockers.append('CLI conditioning assumes no later correction; not a guaranteed outcome')
    elif members['day_start']<asof:blockers.append('In-day forecast lacks a matching received CLI observation')
    output=[]
    for b in bands:
        count=sum((b['lower'] is None or x>=b['lower']) and (b['upper'] is None or x<=b['upper']) for x in rounded)
        output.append(dict(**b,probability=count/len(rounded),member_count=count))
    if abs(sum(p['probability'] for p in output)-1)>1e-9:raise ValueError('US probability mass lost')
    return dict(station=rule['station'],date=rule['date'],metric=rule['metric'],model=model,members=len(native),hours=members['hours'],day_start=members['day_start'],day_end=members['day_end'],forecast_available_at=receipt['available_at'],mean_f=sum(native)/len(native),probabilities=output,cli=cli,blockers=blockers,calibrated=False,execution_eligible=False,note='Ensemble member frequencies are correlated estimates, not binomial confidence bounds or realized profit.')

def scan_contract(rule,models,book,asof):
    if book['slug']!=rule['slug']:raise ValueError('US weather book identity mismatch')
    if not book.get('valid') or book.get('state')!='MARKET_STATE_OPEN':raise ValueError('Book is not open/two-sided')
    if not 0<=asof-book['received_at']<=5 or book.get('exchange_at') is None or not 0<=asof-book['exchange_at']<=5:raise ValueError('Weather book freshness not established')
    values=[]
    for m in models:
        if (m['station'],m['date'],m['metric'])!=(rule['station'],rule['date'],rule['metric']):raise ValueError('Forecast identity mismatch')
        if m['forecast_available_at']>asof:raise ValueError('Forecast arrived after quote decision')
        values.append(next(p['probability'] for p in m['probabilities'] if p['condition']==rule['market_id']))
    if len(values)<2:raise ValueError('At least two forecast systems required')
    result=[]
    for side,prob,price,depth in [('long',min(values),book['offers'][0][0],book['offers'][0][1]),('short',1-max(values),number(1)-number(book['bids'][0][0]),book['bids'][0][1])]:
        p=number(price);q=min(int(number(5)/p),int(depth*.25))
        while q and q*p+conservative_taker_fee(p,q)>5:q-=1
        if not q:continue
        fee=conservative_taker_fee(p,q);cost=q*p+fee
        result.append(dict(slug=rule['slug'],market_id=rule['market_id'],station=rule['station'],date=rule['date'],side=side,probability_min_across_models=prob,model_probabilities=values,quantity=q,price=str(p),fee=str(fee),cost=str(cost),conditional_expected_pnl=float(number(prob)*q-cost),calibrated=False,execution_eligible=False,note='Worst forecast-system frequency, not a statistical lower confidence bound. Conditional expected P&L, not realized profit. No order or paper position created.'))
    return result
