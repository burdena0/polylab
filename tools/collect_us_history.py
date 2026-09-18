"""Freeze a US-only feasibility sample before fetching histories or outcomes."""
import json,time,hashlib,sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_marketdata import get,RateLimited

def main():
    source=ROOT/'data/us/closed-us-fee-era.json'
    discovery=json.loads(source.read_text());now=time.time()
    start=int(datetime.fromisoformat('2026-09-17T04:00:00+00:00').timestamp())
    eligible=[m for m in discovery['response']['markets'] if m.get('closed') is True and start<=datetime.fromisoformat(m['endDate'].replace('Z','+00:00')).timestamp()<=now]
    groups={}
    for m in eligible:groups.setdefault(m.get('category','unknown'),[]).append(m)
    for rows in groups.values():rows.sort(key=lambda m:hashlib.sha256(m['slug'].encode()).hexdigest())
    selected=[]
    while len(selected)<24 and any(groups.values()):
        for category in sorted(groups):
            if groups[category] and len(selected)<24:selected.append(groups[category].pop(0))
    dest=ROOT/'data/us-history'/str(time.time_ns());dest.mkdir(parents=True)
    registration=dict(venue='polymarket_us',created_at=now,discovery_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),markets=selected,start=start,end=int(now),strategies=['momentum','mean_reversion','cash'],lookback_seconds=900,minimum_move='.02',entry_delay_seconds=60,hold_seconds=1800,max_next_quote_gap_seconds=300,entry_budget='5',capital='50',reserve='40',fee_theta='.0695',fee_rounding='half_even_cents_aggregate_upper_bound',slippage_per_side=['0','.005'],selection='Category round robin then SHA256 slug order from first 60 closed US markets ending after current fee start; selected before history/outcome fetch',limitation='Feasibility screen, selected resolved-market universe and incomplete listing. No untouched validation or observed fill depth. EndDate is metadata, not proof of settlement timestamp.')
    (dest/'registration.json').write_text(json.dumps(registration,indent=2))
    report=dict(directory=str(dest),attempted=0,history_points=0,settlements=0,errors=[])
    deadline=time.monotonic()+220
    for m in selected:
        if time.monotonic()>deadline:report['errors'].append({'error':'Collection time budget reached'});break
        end=min(int(now),int(datetime.fromisoformat(m['endDate'].replace('Z','+00:00')).timestamp()))
        for name,path,params in [('history','/v1/price-history',{'symbol':m['slug'],'timestamp.startTimestamp':start,'timestamp.endTimestamp':end,'fidelity':1}),('settlement','/v1/markets/'+m['slug']+'/settlement',None)]:
            try:
                data,receipt=get(path,params);(dest/(m['id']+'-'+name+'.json')).write_text(json.dumps({'response':data,'receipt':receipt}))
                if name=='history':report['history_points']+=len(data.get('history',[]))
                else:report['settlements']+=1
            except Exception as exc:
                report['errors'].append(dict(slug=m['slug'],endpoint=name,error=str(exc)[:160]))
                if isinstance(exc,RateLimited):
                    report['resume_after']=time.time()+exc.retry_after
                    (dest/'collection.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True);return
            time.sleep(2)
        report['attempted']+=1
        (dest/'collection.json').write_text(json.dumps(report,indent=2))
    (dest/'collection.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
