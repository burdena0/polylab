"""Freeze out-of-city US probability transfer tests before price downloads."""
import sys,json,time,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_weather import parse_contract
from polylab.weather_probability import partition

def main():
    source=ROOT/'data/us-calibration-source/us-weather-september-events.json';original=ROOT/'data/us-benter/1789690917159502000/analysis-1789692289582301300/report.json'
    report=json.loads(original.read_text());cfg=report['registration'];events=json.loads(source.read_text())['response']['events'];stations=['KMDW','KLAX','KMIA','KSFO'];groups=[];seen=set()
    for e in events:
        rules=[parse_contract(m) for m in e['markets']]
        if not rules or rules[0]['station'] not in stations or not cfg['test_dates'][0]<=rules[0]['date']<=cfg['test_dates'][1]:continue
        station,day=rules[0]['station'],rules[0]['date']
        if (station,day) in seen or e.get('closed') is not True or any((r['station'],r['date'])!=(station,day) for r in rules):raise ValueError('Event identity mismatch')
        seen.add((station,day));partition([dict(condition=r['market_id'],unit='F',lower=r['lower'],upper=r['upper']) for r in rules]);groups.append(dict(event=e['slug'],station=station,date=day,role='test',rules=rules))
    d=ROOT/'data/us-transfer'/str(time.time_ns());d.mkdir(parents=True)
    registration={**cfg,'created_at':time.time(),'stations':stations,'groups':sorted(groups,key=lambda g:(g['date'],g['station'])),'station':None,'source_study':str(original.relative_to(ROOT)),'source_study_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'source_events_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'frozen_combination':report['combination_model'],'strategies':['benter','market_recalibrated','market_only','mos_only'],'selection':'All four non-NYC stations present in the same official September event archive; all nine September 8–16 dates. No selection by new prices or payouts. Same dates imply shared weather/regime dependence, not independent temporal replication.','adaptation':'Freeze NYC alpha/beta; station MOS uses only July 28–August 16. Market-only recalibration ablation sets alpha=0 and preserves beta; no refitting.','account_design':'Each station/strategy/cost scenario independently starts at $50 with $40 reserve and $200/month expense; never sum as a shared-capital portfolio.','analysis_policy':'Report all registered stations, arms and costs including missing coverage; no P&L tuning or promotion from this test alone.'}
    (d/'registration.json').write_text(json.dumps(registration,indent=2));(d/'events.json').write_bytes(source.read_bytes());(d/'frozen-source-report.json').write_bytes(original.read_bytes())
    print(json.dumps(dict(directory=str(d),events=len(groups),requests=sum(len(g['rules'])*2 for g in groups),stations=stations)))

if __name__=='__main__':main()
