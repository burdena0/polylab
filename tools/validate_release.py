"""Record reproducible cost sensitivity and current public-feed evidence."""
import sys,json,time,gzip,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests
from polylab.research import ROOT,run

agent=json.loads((ROOT/'data'/'agent-comparison-momentum.json').read_text())
checks=[]
for name,config in [('zero_fee',{'fee_bps':0}),('double_fee',{'fee_bps':200}),('strict_freshness',{'allow_unknown_age':False}),('default',{})]:
    report=run(config,agent)
    checks.append(dict(name=name,id=report['id'],config=report['config'],results={k:{f:v[f] for f in ['trades','realized_pnl','open_basis','net_pnl']} for k,v in report['results'].items()}))
base='http://127.0.0.1:8788/api'
weather=requests.get(base+'/weather',timeout=15).json()
paper=requests.get(base+'/paper',timeout=15).json()
files=list(weather['files'])
archive={}
if files:
    name=files[0]
    response=requests.get(base+'/weather/download',params={'file':name},timeout=20);response.raise_for_status()
    records=[json.loads(line) for line in gzip.decompress(response.content).splitlines()]
    archive=dict(file=name,bytes=len(response.content),rows=len(records),first_at=records[0]['snapshot_at'],last_at=records[-1]['snapshot_at'],fresh_rows=sum(r['fresh_for_execution'] for r in records),first_bid_levels=len(records[0]['bids']),first_ask_levels=len(records[0]['asks']))
    r=requests.post(base+'/weather/backtest',json={'file':name},timeout=30)
    archive['backtest_http_status']=r.status_code
    replay=r.json();archive['backtest']=replay if r.status_code!=200 else dict(windows=replay['windows'],results={k:{f:v[f] for f in ['trades','realized_pnl','open_basis']} for k,v in replay['results'].items()},note=replay['note'])
result=dict(at=time.time(),cost_checks=checks,weather=dict(running=weather['running'],connected=weather['connected'],snapshots=weather['snapshots'],files=len(files),initialized_books=weather.get('initialized_books'),selected_tokens=len(weather['markets']),gaps=weather['gaps']),archive=archive,paper=[{k:a.get(k) for k in ['strategy','running','snapshots','cash','realized_pnl','positions','last_message','source_signal']} for a in [paper]+paper.get('other_accounts',[])])
(ROOT/'data'/'release-validation.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps(result,indent=2))
