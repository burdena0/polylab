"""Two bounded public-book observations for a future US weather ladder; no positions."""
import sys,json,time,hashlib,math
from pathlib import Path
from email.utils import parsedate_to_datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_weather import window
from polylab.us_marketdata import get,normalize_book,RateLimited
from polylab.us_accounting import number,conservative_taker_fee
from polylab.us_benter import combine
from polylab.weather_probability import partition

def assess(rules,records,beta):
    if len(records)!=len(rules):return dict(status='incomplete',candidates=[],cache_qualified=False)
    by_slug={r['book']['slug']:r for r in records};asof=max(r['receipt']['received_at'] for r in records);blockers=[];mids=[]
    for rule in rules:
        r=by_slug[rule['slug']];b=r['book'];receipt=r['receipt'];h=receipt.get('public_cache_headers',{})
        if not b['valid'] or b['state']!='MARKET_STATE_OPEN':return dict(status='incomplete_open_ladder',candidates=[],cache_qualified=False)
        mids.append((b['bids'][0][0]+b['offers'][0][0])/2)
        try:
            age=float(h['Age']);server=parsedate_to_datetime(h['Date']).timestamp()
            if not 0<=age<=30 or not -5<=receipt['received_at']-server<=5 or asof-receipt['received_at']+age>45:blockers.append(rule['slug']+': cache timing outside probe bounds')
        except (KeyError,ValueError,TypeError):blockers.append(rule['slug']+': cache age/date unknown')
        if receipt.get('round_trip_seconds',math.inf)>5:blockers.append(rule['slug']+': slow/unknown transport')
        if b['exchange_at'] is None or b['exchange_at']>receipt['received_at']+5:blockers.append(rule['slug']+': unknown/future exchange timestamp')
    if asof-min(r['receipt']['received_at'] for r in records)>45:blockers.append('Ladder receipt span exceeds 45 seconds')
    normalized=[p/sum(mids) for p in mids];p=combine(normalized,normalized,[0,beta]);candidates=[]
    for rule,prob in zip(rules,p):
        b=by_slug[rule['slug']]['book']
        for side,probability,price,depth in [('long',prob,b['offers'][0][0],b['offers'][0][1]),('short',1-prob,number(1)-number(b['bids'][0][0]),b['bids'][0][1])]:
            price=number(price);q=min(int(number(5)/price),int(depth*.25))
            while q and q*price+conservative_taker_fee(price,q)>5:q-=1
            if not q:continue
            net=number(probability)*q-price*q-conservative_taker_fee(price,q)
            if net>=number('.10'):candidates.append(dict(slug=rule['slug'],side=side,probability=probability,price=str(price),quantity=q,expected_dollars=str(net),observed_top_depth=depth))
    return dict(status='observed',asof=asof,cache_qualified=not blockers,blockers=blockers,strict_five_second_ladder=all(r['book']['exchange_at'] is not None and 0<=asof-r['book']['exchange_at']<=5 for r in records),candidates=sorted(candidates,key=lambda r:-float(r['expected_dollars'])),probabilities=p,note='Expected values depend on unvalidated transferred market calibration. Cache-qualified is a disclosed probe classification, not executable-fill proof.')

def main():
    model_path=ROOT/'data/us-benter/1789690917159502000/analysis-1789692289582301300/report.json';beta=json.loads(model_path.read_text())['combination_model']['beta']
    weather=ROOT/'data/us-weather/1789688788485319700/report.json';all_rules=json.loads(weather.read_text())['rules'];grouped={}
    for r in all_rules:
        if r['metric']=='max' and window(r)[0]-21600>time.time()+240:grouped.setdefault((r['station'],r['date']),[]).append(r)
    if not grouped:raise ValueError('No still-future decision ladder in cached US discovery; refresh discovery, do not replay passed opportunities')
    key=sorted(grouped,key=lambda k:(window(grouped[k][0])[0],k))[0];rules=grouped[key];partition([dict(condition=r['market_id'],unit='F',lower=r['lower'],upper=r['upper']) for r in rules])
    dest=ROOT/'data/us-forward-depth'/str(time.time_ns());dest.mkdir(parents=True);registration=dict(created_at=time.time(),rules=rules,station=key[0],date=key[1],selection='Earliest still-future six-hours-before-day decision from cached US rules; deterministic station tie-break, not chosen by prices',beta=beta,alpha=0,model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),rounds=2,minimum_round_delay=60,entry_budget=5,depth_fraction=.25,live_execution=False,paper_positions=False)
    (dest/'registration.json').write_text(json.dumps(registration,indent=2));deadline=time.monotonic()+235;reports=[];errors=[];previous=0
    for round_number in range(2):
        if previous:
            wait=max(0,previous+60-time.time())
            if time.monotonic()+wait>=deadline:break
            time.sleep(wait)
        records=[]
        for rule in rules:
            if time.monotonic()>=deadline:break
            try:
                raw,receipt=get('/v1/markets/'+rule['slug']+'/book');book=normalize_book(raw,rule['slug']);record=dict(raw=raw,receipt=receipt,book=book);records.append(record);(dest/f"{round_number}-{rule['market_id']}.json").write_text(json.dumps(record))
            except Exception as exc:
                errors.append(dict(round=round_number,slug=rule['slug'],error=str(exc)[:180]))
                if isinstance(exc,RateLimited):break
        report=assess(rules,records,beta);reports.append(report);previous=time.time()
        (dest/'report.json').write_text(json.dumps(dict(registration=registration,rounds=reports,errors=errors,positions=0,live_execution=False),indent=2));print(json.dumps(dict(directory=str(dest),round=round_number,result=report)),flush=True)
        if errors:break
    comparison=[]
    if len(reports)==2 and reports[0]['candidates']:
        # Hold signal-time probability and direction fixed. Do not replace the
        # reviewed candidate with the new highest-scoring candidate.
        chosen=reports[0]['candidates'][0];source=next((r for r in records if r['book']['slug']==chosen['slug']),None)
        if source and source['book']['valid']:
            book=source['book'];long=chosen['side']=='long';price=number(book['offers'][0][0]) if long else number(1)-number(book['bids'][0][0]);depth=book['offers'][0][1] if long else book['bids'][0][1];q=min(int(number(5)/price),int(depth*.25))
            while q and q*price+conservative_taker_fee(price,q)>5:q-=1
            net=number(chosen['probability'])*q-price*q-conservative_taker_fee(price,q)
            comparison.append(dict(signal=chosen,later_price=str(price),later_quantity=q,later_expected_dollars=str(net),both_ladders_cache_qualified=reports[0]['cache_qualified'] and reports[1]['cache_qualified'],positions_opened=0))
    final=dict(registration=registration,rounds=reports,errors=errors,delayed_candidate_comparison=comparison,positions=0,live_execution=False,conclusion='Forward depth probe only; no trade, guaranteed fill, or realized profit.')
    (dest/'report.json').write_text(json.dumps(final,indent=2));print(json.dumps(dict(directory=str(dest),comparison=comparison,errors=errors)),flush=True)

if __name__=='__main__':main()
