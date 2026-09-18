"""Register a new US-only MOS/market combination study before price collection."""
import sys,json,time,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_marketdata import get
from polylab.us_weather import parse_contract
from polylab.weather_probability import partition

def main():
    dest=ROOT/'data/us-benter'/str(time.time_ns());dest.mkdir(parents=True)
    protocol=dict(created_at=time.time(),venue='polymarket_us',station='KNYC',forecast_training=['2026-07-28','2026-08-16'],combination_training=['2026-08-17','2026-08-31'],test_dates=['2026-09-08','2026-09-16'],excluded_pilot_dates=['2026-09-01','2026-09-07'],forecast_archive='data/us-mos/1789689723727704700',forecast_rows='data/us-mos/1789689723727704700/calibration-1789689900234570400/report.json',decision_seconds_before_climate_day_start=21600,entry_delay_seconds=60,max_quote_age_seconds=300,entry_budget='5',capital='50',reserve='40',min_expected_dollars='.10',slippage_per_side=['0','.005'],monthly_subscription=200,minimum_combination_dates=10,probability_floor=1e-6,weight_bounds=[0,4],ridge_penalty=.01,ridge_anchor=[0,1],strategies=['mos_only','fixed_blend','benter','market_only','shin_asks'],fit_objective='Mean multiclass negative log likelihood plus .01 times squared distance from market-only weights (0,1); coefficients bounded [0,4]. No P&L tuning.',selection='All KNYC dates within predeclared windows from bounded official US event metadata; no replacement dates after observing coverage or P&L.',availability='MOS runtime+6h assumed; fitted model available after last complete training CLI. Exchange historical settlement publication time unavailable.',fee_scenario='September 17 US fee curve applied counterfactually to earlier prices.',quantity_policy='Whole contracts, historical fill depth unverified; $5 notional capacity assumed.',study_status='Exploratory adaptation motivated by a prior losing pilot; future test prices uninspected at registration, but temperature test errors were previously summarized.',live_execution=False)
    (dest/'protocol.json').write_text(json.dumps(protocol,indent=2))
    raw,receipt=get('/v1/events',dict(tagSlug='weather',closed='true',endDateMin='2026-08-17T00:00:00Z',endDateMax='2026-09-01T23:59:59Z',limit=100))
    (dest/'calibration-events.json').write_text(json.dumps(dict(response=raw,receipt=receipt)))
    source=ROOT/'data/us-calibration-source/us-weather-september-events.json';prior=json.loads(source.read_text())
    (dest/'test-events.json').write_bytes(source.read_bytes())
    groups=[];seen=set()
    for role,doc,bounds in [('calibration',raw,protocol['combination_training']),('test',prior['response'],protocol['test_dates'])]:
        if len(doc['events'])>=100:raise ValueError('Bounded event page full; register pagination before proceeding')
        for event in doc['events']:
            rules=[parse_contract(m) for m in event['markets']]
            if not rules or rules[0]['station']!=protocol['station'] or not bounds[0]<=rules[0]['date']<=bounds[1]:continue
            day=rules[0]['date']
            if event.get('closed') is not True or any((r['station'],r['date'])!=(protocol['station'],day) for r in rules):raise ValueError('Event identity/closed status mismatch')
            if day in seen:raise ValueError('Duplicate event date')
            seen.add(day);partition([dict(condition=r['market_id'],unit='F',lower=r['lower'],upper=r['upper']) for r in rules])
            groups.append(dict(event=event['slug'],date=day,role=role,rules=rules))
    registration={**protocol,'groups':sorted(groups,key=lambda g:g['date']),'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.glob('*events.json')}}
    (dest/'registration.json').write_text(json.dumps(registration,indent=2))
    print(json.dumps(dict(directory=str(dest),dates=[(g['date'],g['role']) for g in registration['groups']],requests=sum(len(g['rules'])*2 for g in groups))),flush=True)

if __name__=='__main__':main()
