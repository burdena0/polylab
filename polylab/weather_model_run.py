"""Apply the temperature model to actual rule and ensemble receipts, without paper promotion."""
import json,time
from pathlib import Path
from collections import Counter
from .research import ROOT
from .weather_probability import parse_rule,parse_band,partition,daily_members,distribution,candidates
from .fees import observed_schedule
from .weather_rules import apply_review

def run(quotes=None):
    source=json.loads((ROOT/'data/public-inputs/latest.json').read_text(encoding='utf-8'));ensemble=json.loads((ROOT/'data/ensemble/latest.json').read_text(encoding='utf-8'));asof=time.time();results=[];rejected=[]
    forecasts={(r['station'],r['model']):r for r in ensemble['receipts'] if 'error' not in r}
    receipts={r['file']:r for r in source['receipts'] if 'error' not in r};quotes=quotes or [];by_condition={q['condition']:q for q in quotes}
    for name,receipt in receipts.items():
        if not name.startswith('event-'):continue
        events=json.loads((Path(source['directory'])/name).read_text(encoding='utf-8'))
        for event in events:
            try:
                markets=event['markets'];rules=[apply_review(parse_rule(m),asof) for m in markets];rule=rules[0];bands=partition([parse_band(m) for m in markets])
                keys=['station','date','metric','unit','sampling','revision_cutoff','fallback']
                if any(any(r[k]!=rule[k] for k in keys) for r in rules):raise ValueError('Mismatched settlement definitions within ladder')
                if not any(station==rule['station'] for station,model in forecasts):raise ValueError('No ensemble receipt for this settlement station')
                for (station,model),forecast_receipt in forecasts.items():
                    if station!=rule['station']:continue
                    forecast=json.loads((Path(ensemble['directory'])/forecast_receipt['file']).read_text(encoding='utf-8'));members=daily_members(forecast,rule,forecast_receipt['available_at'],asof)
                    result=distribution(members,rule,bands,model=model,asof=asof);result.update(event=event['slug'],rule=rule,forecast_file=str(Path(ensemble['directory'])/forecast_receipt['file']),forecast_sha256=forecast_receipt['sha256'],forecast_available_at=forecast_receipt['available_at'],candidate_scan=[],quote_rejections=[])
                    for m in markets:
                        if m['conditionId'] not in by_condition:continue
                        try:
                            quote={**by_condition[m['conditionId']],'fee_schedule':observed_schedule(m,receipt['available_at'])}
                            result['candidate_scan'].extend(candidates(result,[quote],asof))
                        except ValueError as exc:result['quote_rejections'].append(dict(condition=m['conditionId'],reason=str(exc)))
                    result['candidate_scan'].sort(key=lambda r:r['expected_net_pnl'],reverse=True);results.append(result)
            except (ValueError,KeyError) as exc:rejected.append(dict(event=event.get('slug'),reason=str(exc)))
    root=ROOT/'data/weather-models';dest=root/str(time.time_ns());dest.mkdir(parents=True)
    report=dict(created_at=asof,directory=str(dest),source_rules=source['directory'],source_ensemble=ensemble['directory'],models=results,rejected=rejected,quote_pairs_received=len(quotes),blockers=dict(Counter(b for r in results for b in r['blockers'])),realized_pnl=None,execution_eligible=False,note='Research probability scans only. Uncalibrated models and unverified settlement conventions are not promoted to paper accounts. Expected P&L is conditional on model probabilities and is never reported as realized profit. No historical weather-profit backtest is implied.')
    (dest/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False));tmp=root/f'latest-{time.time_ns()}.tmp';tmp.write_text(json.dumps({'directory':str(dest),'created_at':asof}));tmp.replace(root/'latest.json');return report

def latest():
    pointer=json.loads((ROOT/'data/weather-models/latest.json').read_text());return json.loads((Path(pointer['directory'])/'report.json').read_text())

if __name__=='__main__':
    r=run();print(json.dumps(dict(directory=r['directory'],model_cases=len(r['models']),rejected=r['rejected'],blockers=r['blockers'])))
