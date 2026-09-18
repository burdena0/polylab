"""Bounded, source-backed collection of external inputs for net-P&L research."""
import sys,csv,io,json,hashlib,time,zipfile,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests,pyarrow as pa,pyarrow.parquet as pq
from polylab.research import ROOT
HEADERS={'User-Agent':'PolyLab local public-data research (no exchange orders)'}

def fetch(url,params=None,limit=25_000_000):
    r=requests.get(url,params=params,headers=HEADERS,timeout=20,stream=True);r.raise_for_status();parts=[];size=0
    for chunk in r.iter_content(65536):
        size+=len(chunk)
        if size>limit:raise ValueError('Response exceeds collection budget')
        parts.append(chunk)
    return b''.join(parts),r.url

def spot():
    dest=ROOT/'data/spot';dest.mkdir(exist_ok=True);records=[];candles=[]
    for month in ['2026-03','2026-04','2026-05']:
        name='BTCUSDT-1m-'+month+'.zip';url='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/'+name;path=dest/name
        try:
            raw=path.read_bytes() if path.exists() else fetch(url)[0]
            check=fetch(url+'.CHECKSUM',limit=4096)[0].decode().split()[0];digest=hashlib.sha256(raw).hexdigest()
            if digest!=check:raise ValueError('Publisher checksum mismatch')
            if not path.exists():path.write_bytes(raw)
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                expected=name.replace('.zip','.csv')
                if archive.namelist()!=[expected] or archive.getinfo(expected).file_size>40_000_000:raise ValueError('Unexpected archive contents')
                text=archive.read(expected).decode()
                for row in csv.reader(io.StringIO(text)):
                    # Official spot archives use microseconds from January 2025.
                    opened=int(row[0])/1_000_000;closed=int(row[6])/1_000_000;values=[float(row[i]) for i in [1,2,3,4,5]]
                    if int(opened)%60 or not 59<=closed-opened<60 or min(values[:4])<=0 or values[2]>min(values[0],values[3]) or values[1]<max(values[0],values[3]):raise ValueError('Invalid candle')
                    candles.append(dict(open_at=opened,close_at=closed,open=values[0],high=values[1],low=values[2],close=values[3],volume=values[4]))
            records.append(dict(url=url,sha256=digest,checksum_verified=True,bytes=len(raw),month=month))
            print('Verified spot archive '+month,flush=True)
        except Exception as exc:records.append(dict(url=url,error=type(exc).__name__+': '+str(exc)[:180]))
    candles.sort(key=lambda r:r['open_at']);times=[c['open_at'] for c in candles]
    if len(set(times))!=len(times):raise ValueError('Duplicate candle times')
    gaps=sum(b-a!=60 for a,b in zip(times,times[1:]))
    if candles:pq.write_table(pa.Table.from_pylist(candles),dest/'btcusdt-1m.parquet')
    receipt=dict(collected_at=time.time(),files=records,candles=len(candles),minute_gaps=gaps,source='Binance official public spot archives',note='BTC/USDT spot is an external proxy, not the Polymarket Chainlink settlement oracle. Closed candles need an availability lag before entering any feature.')
    (dest/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)

def weather():
    dest=ROOT/'data/external-weather'/str(time.time_ns());dest.mkdir(parents=True)
    manifest=json.loads((ROOT/'data/weather/manifest.json').read_text());events=sorted({m['event'] for m in manifest['markets']})[:12];receipts=[];stations=set()
    for slug in events:
        try:
            raw,url=fetch('https://gamma-api.polymarket.com/events',{'slug':slug},8_000_000);items=json.loads(raw)
            if not items or items[0]['slug']!=slug:raise ValueError('Event identity mismatch')
            (dest/(slug+'.json')).write_bytes(raw)
            for market in items[0]['markets']:
                description=market.get('description','');stations.update(s.upper() for s in re.findall(r'weather\.gov/[^\s]+[?&]site=([a-zA-Z0-9]{4})',description))
            receipts.append(dict(kind='settlement_rules',url=url,received_at=time.time(),sha256=hashlib.sha256(raw).hexdigest()))
        except Exception as exc:receipts.append(dict(kind='settlement_rules',slug=slug,error=str(exc)[:160]))
    for station in sorted(stations)[:8]:
        try:
            raw,url=fetch('https://api.weather.gov/stations/'+station);location=json.loads(raw);(dest/(station+'-metadata.json')).write_bytes(raw)
            lon,lat=location['geometry']['coordinates'][:2]
            for name,url,params in [('observations','https://api.weather.gov/stations/'+station+'/observations',{'limit':200}),('forecast','https://api.open-meteo.com/v1/forecast',{'latitude':lat,'longitude':lon,'hourly':'temperature_2m,relative_humidity_2m,cloud_cover,wind_speed_10m','forecast_days':3,'timezone':'UTC'})]:
                raw,actual=fetch(url,params,8_000_000);(dest/(station+'-'+name+'.json')).write_bytes(raw)
                receipts.append(dict(kind=name,station=station,url=actual,received_at=time.time(),sha256=hashlib.sha256(raw).hexdigest()))
            print('Recorded station inputs '+station,flush=True)
        except Exception as exc:receipts.append(dict(kind='station_inputs',station=station,error=type(exc).__name__+': '+str(exc)[:160]))
    (dest/'receipt.json').write_text(json.dumps(dict(created_at=time.time(),receipts=receipts,note='Snapshots available only at receipt time. Current observations may contain revisions; these files are not point-in-time historical forecasts. Only NOAA station identifiers explicitly found in actual settlement rules are mapped.'),indent=2))
    print(json.dumps(dict(weather_directory=str(dest),stations=sorted(stations),success=sum('error' not in r for r in receipts),failures=[r for r in receipts if 'error' in r])),flush=True)

if __name__=='__main__':spot();weather()
