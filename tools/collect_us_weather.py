"""Bounded US-contract/CLI/ensemble archive and conditional forecast-edge scan."""
import sys,json,time,hashlib,re,threading
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import defaultdict,Counter
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_marketdata import get,normalize_book,RateLimited
from polylab.us_weather import STATIONS,parse_contract,parse_cli,probabilities,scan_contract
from polylab.weather_probability import partition

MODELS={'gfs_seamless':31,'ecmwf_ifs025':51,'icon_global':40}

def fetch(url,params=None):
    if not (re.fullmatch(r'https://api.weather.gov/(?:stations/K[A-Z]{3}|products/types/CLI/locations/[A-Z]{3}|products/[a-f0-9-]{36})',url) or url=='https://ensemble-api.open-meteo.com/v1/ensemble'):raise ValueError('Unapproved weather data URL')
    with requests.Session() as session:
        session.trust_env=False
        with session.get(url,params=params,headers={'User-Agent':'PolyLab public weather research'},timeout=(5,12),stream=True,allow_redirects=False) as response:
            if 300<=response.status_code<400:raise ValueError('Weather source redirect rejected')
            if response.status_code==429:raise RateLimited(response.headers.get('Retry-After'))
            response.raise_for_status();raw=b''
            for chunk in response.iter_content(65536):
                raw+=chunk
                if len(raw)>8_000_000:raise ValueError('Weather response budget exceeded')
            return json.loads(raw),raw,dict(url=response.url,available_at=time.time(),sha256=hashlib.sha256(raw).hexdigest())

def collect():
    root=ROOT/'data/us-weather';root.mkdir(exist_ok=True)
    if sum(p.stat().st_size for p in root.rglob('*.json'))>500_000_000:raise ValueError('US weather archive budget reached')
    dest=root/str(time.time_ns());dest.mkdir();started=time.time();deadline=time.monotonic()+240
    report=dict(directory=str(dest),started_at=started,venue='polymarket_us',rules=[],observations=[],models=[],candidates=[],errors=[],receipts=[],live_execution=False,calibrated=False,realized_pnl=None,code_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['tools/collect_us_weather.py','polylab/us_weather.py']})
    def save():
        report.update(completed_at=time.time(),blockers=dict(Counter(b for m in report['models'] for b in m['blockers'])))
        (dest/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False));tmp=root/'latest.tmp';tmp.write_text(json.dumps({'directory':str(dest)}));tmp.replace(root/'latest.json')
    def archive(name,url,params=None):
        if time.monotonic()>deadline:raise TimeoutError('US weather collection time budget reached')
        data,raw,receipt=fetch(url,params);(dest/name).write_bytes(raw);report['receipts'].append(dict(**receipt,file=name));time.sleep(.5);return data,receipt
    try:
        now=datetime.now(timezone.utc);markets=[];groups=defaultdict(list)
        for page in range(3):
            raw,receipt=get('/v1/markets',{'active':'true','closed':'false','limit':100,'offset':page*100,'endDateMin':now.isoformat(),'endDateMax':(now+timedelta(days=3)).isoformat()})
            (dest/f'markets-{page}.json').write_text(json.dumps(raw));report['receipts'].append(dict(**receipt,file=f'markets-{page}.json'));markets.extend(raw['markets']);time.sleep(2)
            if len(raw['markets'])<100:break
        seen=set()
        for m in markets:
            if m['id'] in seen or m.get('category') not in ['climate','weather']:continue
            seen.add(m['id'])
            try:
                rule=parse_contract(m);report['rules'].append(rule);groups[(rule['station'],rule['date'],rule['metric'])].append(rule)
            except ValueError as exc:report['errors'].append(dict(slug=m['slug'],phase='rules',error=str(exc)))
        stations=sorted({r['station'] for r in report['rules']});forecasts={};cli_records=defaultdict(list)
        for station in stations:
            try:
                metadata,_=archive(station+'-station.json','https://api.weather.gov/stations/'+station)
                if metadata['properties']['stationIdentifier']!=station:raise ValueError('Station metadata mismatch')
                lon,lat=metadata['geometry']['coordinates'];elevation=metadata['properties']['elevation']
                if elevation['unitCode']!='wmoUnit:m':raise ValueError('Station elevation unit mismatch')
                index,_=archive(station+'-cli-index.json','https://api.weather.gov/products/types/CLI/locations/'+STATIONS[station]['cli'])
                products=sorted(index['@graph'],key=lambda r:r['issuanceTime'],reverse=True)[:3]
                for item in products:
                    data,receipt=archive(item['id']+'-cli.json','https://api.weather.gov/products/'+item['id'])
                    try:
                        observation=parse_cli(data,station,receipt['available_at']);report['observations'].append(observation);cli_records[station].append(observation)
                    except ValueError as exc:report['errors'].append(dict(station=station,phase='cli_parse',error=str(exc)))
                for model,expected in MODELS.items():
                    try:
                        name=station+'-'+model+'.json';forecast,receipt=archive(name,'https://ensemble-api.open-meteo.com/v1/ensemble',dict(latitude=lat,longitude=lon,elevation=elevation['value'],hourly='temperature_2m',models=model,forecast_days=3,past_days=1,timezone='UTC'))
                        count=len([k for k in forecast['hourly'] if k.startswith('temperature_2m')])
                        if count!=expected:raise ValueError(f'Expected {expected} members; got {count}')
                        forecasts[(station,model)]=(forecast,receipt)
                    except (requests.RequestException,ValueError) as exc:report['errors'].append(dict(station=station,model=model,phase='ensemble',error=str(exc)[:180]))
            except (requests.RequestException,ValueError,KeyError) as exc:report['errors'].append(dict(station=station,phase='station_sources',error=str(exc)[:180]))
        for (station,date,metric),rules in groups.items():
            try:
                bands=partition([dict(condition=r['market_id'],lower=r['lower'],upper=r['upper'],label=r['label'],unit='F') for r in rules]);asof=time.time()
                matching=[o for o in cli_records[station] if o['date']==date and o['available_at']<=asof]
                cli=max(matching,key=lambda o:o['issued_at']) if matching else None
                for model in MODELS:
                    if (station,model) not in forecasts:continue
                    forecast,receipt=forecasts[(station,model)];result=probabilities(forecast,receipt,rules[0],bands,model,asof,cli)
                    result.update(forecast_file=station+'-'+model+'.json',forecast_sha256=receipt['sha256']);report['models'].append(result)
            except (ValueError,KeyError) as exc:report['errors'].append(dict(station=station,date=date,phase='model',error=str(exc)))
        # Models are computed before quote receipts, preserving availability.
        metadata_by_slug={m['slug']:m for m in markets}
        # Use the bounded quote budget first on two-sided listings and future
        # climate days, before today's mostly one-sided near-settlement books.
        ordered_rules=sorted(report['rules'],key=lambda r:(not bool(metadata_by_slug[r['slug']].get('bestBidQuote') and metadata_by_slug[r['slug']].get('bestAskQuote')),-int(r['date'].replace('-','')),r['slug']))
        for rule in ordered_rules:
            if time.monotonic()>deadline:report['errors'].append(dict(phase='quotes',error='Collection time budget reached'));break
            models=[m for m in report['models'] if (m['station'],m['date'],m['metric'])==(rule['station'],rule['date'],rule['metric'])]
            if len(models)<2:continue
            try:
                raw,receipt=get('/v1/markets/'+rule['slug']+'/book');name=rule['market_id']+'-book.json';(dest/name).write_text(json.dumps(raw));report['receipts'].append(dict(**receipt,file=name))
                book=dict(**normalize_book(raw,rule['slug']),received_at=receipt['received_at']);report['candidates'].extend(scan_contract(rule,models,book,time.time()))
            except (requests.RequestException,ValueError,KeyError) as exc:report['errors'].append(dict(slug=rule['slug'],phase='quotes',error=str(exc)[:180]))
            time.sleep(2)
    except (RateLimited,TimeoutError) as exc:
        report['errors'].append(dict(phase='batch',error=str(exc)))
        if isinstance(exc,RateLimited):report['resume_after']=time.time()+exc.retry_after
    finally:
        report['candidates'].sort(key=lambda r:r['conditional_expected_pnl'],reverse=True);save()
    return report

if __name__=='__main__':
    r=collect();print(json.dumps({k:r[k] for k in ['directory','blockers','errors']}));print(json.dumps(dict(rules=len(r['rules']),observations=len(r['observations']),models=len(r['models']),candidates=len(r['candidates']))))
