"""Evaluate frozen candidates once on the registered, unused market rows."""
import sys,json,hashlib,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT,features
from polylab.risk_replay import simulate

root=ROOT/'data/profit-study-v1';h=json.loads((root/'history.json').read_text());reg=h['registration']
for name,digest in reg['code_hashes'].items():
    if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen candidate code changed: '+name)
rows=[]
for m in h['markets']:
    f=features(m)
    if f:rows.append(dict(market=m,features=f))
results={v:simulate(rows,{},v) for v in reg['primary_comparison']+reg['secondary']}
stress={v:simulate(rows,{},v,{'fee_bps':200}) for v in reg['primary_comparison']}
out=root/'runs'/str(time.time_ns());out.mkdir(parents=True)
report=dict(created_at=time.time(),source_sha256=hashlib.sha256((root/'history.json').read_bytes()).hexdigest(),registration=reg,selected=len(reg['conditions']),verified=len(h['markets']),valid_decisions=len(rows),failed=h['failed'],results=results,fee_stress_200bps=stress,execution_eligible=False,conclusion='Price-replay evidence only. Historical fills/freshness are unproven; prospective paper comparison remains necessary.')
(out/'report.json').write_text(json.dumps(report,allow_nan=False));(root/'latest.json').write_text(json.dumps({'run':out.name}))
print(json.dumps(dict(path=str(out/'report.json'),selected=report['selected'],verified=report['verified'],valid_decisions=len(rows),results={k:{f:v[f] for f in ['trades','realized_pnl','equity','open_basis','max_drawdown']} for k,v in results.items()},stress={k:v['realized_pnl'] for k,v in stress.items()}),indent=2))
