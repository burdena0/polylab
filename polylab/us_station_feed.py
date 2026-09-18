"""Compare actual receipt times of the same public station reports."""
import hashlib,re
from datetime import datetime

def iso(value):return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()

def observation(station,timestamp,raw,temp,received,source):
    if timestamp>received:raise ValueError('Observation timestamp follows local receipt')
    text=re.sub(r'^(?:METAR|SPECI)\s+','',raw.strip())
    text=' '.join(text.split())
    if not text.startswith(station+' '):raise ValueError('Raw observation station mismatch')
    key=hashlib.sha256((station+'|'+str(int(timestamp))+'|'+text).encode()).hexdigest()
    return dict(station=station,observed_at=timestamp,raw_message=text,temperature=temp,available_at=received,source=source,report_key=key,
                observation_age_seconds=received-timestamp,role='Station observation covariate, not a CLI daily extreme or exchange settlement')

def normalize(document,receipt,stations,source,station=None):
    result=[]
    if source=='awc':
        for row in document:
            if row['icaoId'] not in stations:raise ValueError('Unrequested station')
            value=observation(row['icaoId'],float(row['obsTime']),row['rawOb'],row.get('temp'),receipt['received_at'],source)
            value['provider_receipt_time']=row.get('receiptTime')
            result.append(value)
    elif source=='nws':
        row=document['properties']
        if station not in stations or row['station']!='https://api.weather.gov/stations/'+station:raise ValueError('NWS station identity')
        result.append(observation(station,iso(row['timestamp']),row['rawMessage'],row.get('temperature'),receipt['received_at'],source))
    else:raise ValueError('Unknown source')
    return result

def paired_snapshot(observations,stations):
    result=[]
    for station in stations:
        latest={source:max((o for o in observations if o['station']==station and o['source']==source),key=lambda o:o['observed_at'],default=None) for source in ['awc','nws']}
        a,n=latest['awc'],latest['nws']
        result.append(dict(station=station,awc=a,nws=n,awc_newer_observation_seconds=a['observed_at']-n['observed_at'] if a and n else None,
                           same_report=bool(a and n and a['report_key']==n['report_key']),profit=None))
    return result
