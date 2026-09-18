"""Registered comparison; reads old immutable archive, creates new results."""
import json,sys,time,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_allocation import load
from polylab.us_multiband_replay import simulate
from polylab.us_multiband import event_payoffs

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    root=Path(sys.argv[1]).resolve();registration=json.loads((root/'registration.json').read_text())
    for name,sha in json.loads((root/'code-freeze.json').read_text())['sha256'].items():
        if digest(ROOT/name)!=sha:raise ValueError('Frozen code/input changed '+name)
    source=ROOT/registration['source']
    for name,sha in json.loads((source/'code-freeze.json').read_text())['sha256'].items():
        if digest(ROOT/name)!=sha:raise ValueError('Frozen parent input changed '+name)
    cfg,groups,coverage,hashes=load(source,ROOT)
    for g in groups:event_payoffs([],g['rules'])
    results=[];groupmap={(g['station'],g['target']):g for g in groups}
    for slip in registration['slippage_per_side']:
        for method in registration['strategies']:
            r=simulate(groups,cfg,method,slip);states=[]
            for decision in r['decisions']:
                for station in sorted(set(l['station'] for l in decision['selected'])):
                    legs=[l for l in decision['selected'] if l['station']==station]
                    states.append(dict(t=decision['t'],station=station,legs=len(legs),scenario_payoffs=event_payoffs(legs,groupmap[(station,decision['t'])]['rules'])))
            r['event_scenarios']=states;results.append(r)
    dest=root/('analysis-'+str(time.time_ns()));dest.mkdir()
    report=dict(created_at=time.time(),registration=registration,source_registration_sha256=digest(source/'registration.json'),source_hashes=hashes,coverage=coverage,results=results,live_execution=False)
    (dest/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(directory=str(dest),complete_groups=sum(c['complete_signal'] for c in coverage),results=[dict(strategy=r['strategy'],slippage=r['slippage_per_side'],profit=r['realized_pnl'],entries=r['entries'],open_basis=r['open_basis'],multi_leg_city_decisions=sum(s['legs']>1 for s in r['event_scenarios'])) for r in results]),indent=2))

if __name__=='__main__':main()
