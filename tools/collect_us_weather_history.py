"""Frozen historical US weather pilot. Resumable bounded collection, no orders."""
import sys,json,time,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_weather import parse_contract,window
from polylab.weather_probability import partition
from polylab.us_marketdata import get,RateLimited

def main():
    if len(sys.argv)>1:dest=Path(sys.argv[1]).resolve();registration=json.loads((dest/'registration.json').read_text())
    else:
        source=ROOT/'data/us-calibration-source/us-weather-september-events.json';events=json.loads(source.read_text())['response']['events'];groups=[]
        for event in events:
            rules=[parse_contract(m) for m in event['markets']]
            if not rules or rules[0]['station']!='KNYC':continue
            if any((r['station'],r['date'])!=(rules[0]['station'],rules[0]['date']) for r in rules):raise ValueError('Mixed event identity')
            partition([dict(condition=r['market_id'],unit='F',lower=r['lower'],upper=r['upper']) for r in rules])
            groups.append(dict(event=event['slug'],date=rules[0]['date'],rules=rules))
        groups=sorted(groups,key=lambda g:g['date'])[:6]
        dest=ROOT/'data/us-weather-history'/str(time.time_ns());dest.mkdir(parents=True)
        registration=dict(created_at=time.time(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),groups=groups,selection='First six available KNYC September dates from complete bounded tagged-event query; not chosen by prices/outcomes',training_start='2026-07-28',training_end='2026-08-26',validation_start='2026-08-27',validation_end='2026-08-31',test_start='2026-09-01',test_end='2026-09-16',forecast_cycle='Previous UTC date at 12Z',assumed_forecast_publication_lag_hours=6,decision_seconds_before_climate_day_start=21600,entry_delay_seconds=60,max_quote_age_seconds=300,entry_budget='5',capital='50',reserve='40',min_expected_dollars='.10',models=['GFS','NAM'],fee_scenario='Current September 17 fee applied counterfactually; not verified historical fees',slippage_per_side=['0','.005'],quantity_policy='Whole simulated contracts; historical depth unavailable',live_execution=False)
        (dest/'registration.json').write_text(json.dumps(registration,indent=2))
    report_path=dest/'collection.json';report=json.loads(report_path.read_text()) if report_path.exists() else dict(directory=str(dest),errors=[],files=0)
    deadline=time.monotonic()+235
    for g in registration['groups']:
        for rule in g['rules']:
            target=int(window(rule)[0]-21600)
            requests=[('history','/v1/price-history',dict(symbol=rule['slug'],**{'timestamp.startTimestamp':target-1800,'timestamp.endTimestamp':target+2700,'fidelity':1})),('settlement','/v1/markets/'+rule['slug']+'/settlement',None)]
            for name,path,params in requests:
                out=dest/(rule['market_id']+'-'+name+'.json')
                if out.exists():continue
                if time.monotonic()>deadline:report['status']='partial_time_budget';report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True);return
                try:
                    raw,receipt=get(path,params);out.write_text(json.dumps(dict(response=raw,receipt=receipt)));report['files']+=1
                except Exception as exc:
                    report['errors'].append(dict(slug=rule['slug'],endpoint=name,error=str(exc)[:160]))
                    if isinstance(exc,RateLimited):
                        report.update(status='partial_cooldown',resume_after=time.time()+exc.retry_after);report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True);return
                report_path.write_text(json.dumps(report,indent=2))
    report['status']='complete' if report['files']==sum(len(g['rules'])*2 for g in registration['groups']) else 'partial_missing';report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)

if __name__=='__main__':main()
