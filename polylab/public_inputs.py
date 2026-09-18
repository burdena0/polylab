"""Point-in-time public weather inputs tied to the actual archived market rules."""
import hashlib,json,math,re,time,threading
from urllib.parse import urlparse,parse_qs
import requests
from .research import ROOT

def stations_from_rules(description):
    result=set()
    for url in re.findall(r'https?://[^\s<>"\)]+',description):
        parsed=urlparse(url.rstrip('.,;'))
        if parsed.hostname not in ('weather.gov','www.weather.gov'):continue
        for station in parse_qs(parsed.query).get('site',[]):
            if re.fullmatch('[A-Za-z0-9]{4}',station):result.add(station.upper())
    return result

def collect(stop=None):
    stop=stop or threading.Event();root=ROOT/'data/public-inputs';root.mkdir(parents=True,exist_ok=True)
    if sum(p.stat().st_size for p in root.rglob('*.json'))>500_000_000:raise ValueError('Weather input archive reached 500 MB limit')
    dest=root/str(time.time_ns());dest.mkdir();started=time.monotonic();receipts=[];last_request=0.
    def save_json(name,url,params=None):
        nonlocal last_request
        if stop.is_set() or time.monotonic()-started>240:raise TimeoutError('Collection stopped or four-minute budget reached')
        stop.wait(max(0,1-(time.monotonic()-last_request)));last_request=time.monotonic()
        entry=dict(file=name,url=url,params=params,requested_at=time.time());receipts.append(entry)
        try:
            chunks=[];size=0
            with requests.get(url,params=params,headers={'User-Agent':'PolyLab local public market research'},timeout=(5,8),stream=True) as response:
                entry['url']=response.url;response.raise_for_status()
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>8_000_000 or time.monotonic()-started>240:raise ValueError('Public response exceeded bounded collection budget')
                    chunks.append(chunk)
                raw=b''.join(chunks) if response.status_code!=204 else b'[]'
            result=json.loads(raw);entry.update(available_at=time.time(),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw));(dest/name).write_bytes(raw)
            return result
        except Exception as exc:entry.update(error=type(exc).__name__+': '+str(exc)[:180]);raise
    mappings=[];stations={};errors=[]
    try:
        manifest=json.loads((ROOT/'data/weather/manifest.json').read_text());slugs=sorted({m['event'] for m in manifest['markets']})[:12]
        for index,slug in enumerate(slugs):
            try:
                events=save_json(f'event-{index}.json','https://gamma-api.polymarket.com/events',{'slug':slug})
                event=next(e for e in events if e.get('slug')==slug)
                for m in event['markets']:
                    ids=stations_from_rules(m.get('description',''))
                    mappings.append(dict(event=slug,condition=m['conditionId'],stations=sorted(ids),rules_file=f'event-{index}.json',rules_sha256=hashlib.sha256(m.get('description','').encode()).hexdigest()))
                    for station in ids:stations[station]=None
            except Exception as exc:errors.append(str(exc)[:160])
        ids=sorted(stations)[:12]
        if ids:
            metadata=save_json('station-metadata.json','https://aviationweather.gov/api/data/stationinfo',{'ids':','.join(ids),'format':'json'})
            for s in metadata:
                if s.get('icaoId') in stations and all(isinstance(s.get(k),(int,float)) and math.isfinite(s[k]) for k in ['lat','lon']):stations[s['icaoId']]=s
            for kind,extra in [('metar',{'hours':6}),('taf',{})]:
                try:save_json(kind+'.json','https://aviationweather.gov/api/data/'+kind,{'ids':','.join(ids),'format':'json',**extra})
                except Exception as exc:errors.append(str(exc)[:160])
            for station in ids:
                if not stations[station]:errors.append('No verified coordinates for '+station);continue
                s=stations[station]
                try:
                    save_json(station+'-forecast.json','https://api.open-meteo.com/v1/forecast',{'latitude':s['lat'],'longitude':s['lon'],'hourly':'temperature_2m,relative_humidity_2m,cloud_cover,wind_speed_10m','forecast_days':3,'timezone':'UTC'})
                    if s.get('country')=='US':save_json(station+'-noaa.json','https://api.weather.gov/stations/'+station+'/observations',{'limit':100})
                except Exception as exc:errors.append(str(exc)[:160])
    except Exception as exc:errors.append(str(exc)[:160])
    report=dict(created_at=time.time(),directory=str(dest),mappings=mappings,stations=sorted(stations),mapped_stations=[k for k,v in stations.items() if v],receipts=receipts,errors=errors,complete=not errors,note='Every input is available no earlier than its receipt timestamp. METAR is a covariate, not automatically the contractual resolution source. Current model forecasts are not historical vintage forecasts. Only station IDs in actual weather.gov settlement-rule URLs are mapped; unsupported rules remain unmapped.')
    (dest/'receipt.json').write_text(json.dumps(report,indent=2));tmp=root/'latest.tmp';tmp.write_text(json.dumps(report,indent=2));tmp.replace(root/'latest.json');return report

class WeatherInputs:
    def __init__(self,quote_provider=None):self.stop_event=threading.Event();self.thread=None;self.lock=threading.RLock();self.state={'running':False};self.quote_provider=quote_provider
    def snapshot(self):
        with self.lock:return json.loads(json.dumps(self.state))
    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return self.snapshot()
            self.stop_event.clear();self.state['running']=True;self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self.snapshot()
    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=12)
        return self.snapshot()
    def loop(self):
        try:
            while not self.stop_event.is_set():
                try:
                    report=collect(self.stop_event)
                    with self.lock:self.state.update(last_run=report['created_at'],directory=report['directory'],stations=report['mapped_stations'],errors=report['errors'],complete=report['complete'])
                    if not self.stop_event.is_set():
                        from .ensemble_archive import collect_if_due
                        ensemble=collect_if_due(self.stop_event)
                        with self.lock:self.state.update(ensemble_directory=ensemble['directory'],ensemble_complete=ensemble['complete'],ensemble_files=len(ensemble['receipts']))
                        if not self.stop_event.is_set():
                            from .weather_model_run import run
                            analysis=run(self.quote_provider() if self.quote_provider else [])
                            with self.lock:self.state.update(model_directory=analysis['directory'],model_cases=len(analysis['models']),model_quote_pairs=analysis['quote_pairs_received'])
                except Exception as exc:
                    with self.lock:self.state['error']=str(exc)[:180]
                self.stop_event.wait(900)
        finally:
            with self.lock:self.state['running']=False

if __name__=='__main__':
    r=collect();print(json.dumps({k:r[k] for k in ['directory','mapped_stations','errors','complete']}))
