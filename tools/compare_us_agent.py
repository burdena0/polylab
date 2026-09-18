"""Exploratory local-agent ablation on the frozen US feasibility sample."""
import sys,json,time,hashlib,math
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_replay import normalize_history,opportunity,replay
from polylab.agent import review,MODEL,PROMPT

def main():
    source=Path(sys.argv[1]).resolve();cfg=json.loads((source/'registration.json').read_text());histories={};packets=[];mapping={}
    for m in cfg['markets']:
        p=source/(m['id']+'-history.json')
        if not p.exists():continue
        d=json.loads(p.read_text());from urllib.parse import urlparse,parse_qs
        u=urlparse(d['receipt']['url'])
        if u.hostname!='gateway.polymarket.us' or parse_qs(u.query).get('symbol')!=[m['slug']]:raise ValueError('History identity mismatch')
        end=min(cfg['end'],datetime.fromisoformat(m['endDate'].replace('Z','+00:00')).timestamp())
        histories[m['slug']]=normalize_history(d['response'],cfg['start'],end)[0]
    for kind in ['momentum','mean_reversion']:
        for slug,points in sorted(histories.items()):
            o=opportunity(points,cfg,kind)
            if not o:continue
            past=[p for p in points if p['t']<=o['signal_t']];last=past[-1];key=str(len(packets))
            packet=dict(id=key,strategy=kind,side=o['side'],signal_move=o['move'],bid=last['bid'],ask=last['ask'],spread=last['ask']-last['bid'],model_probability=None,liquidity=None,observations=len(past),recent_midpoints=[dict(seconds_before_signal=o['signal_t']-p['t'],mid=p['mid']) for p in past[-20:]],note='No calibrated probability or historical depth is available. Future prices and outcomes are withheld.')
            packets.append(packet);mapping[key]=dict(strategy=kind,slug=slug,signal_t=o['signal_t'])
    dest=ROOT/'data/us-agent'/str(time.time_ns());dest.mkdir(parents=True)
    registration=dict(created_at=time.time(),sample=str(source),model=MODEL,prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),packets=packets,mapping=mapping,arms=['no_agent','spread_rule','agent','agent_with_delay'],rule='Allow only signal spread <= .03 and selected-side signal price in [.15,.85]',latency='Add the full measured request wall time to the baseline 60-second delay for every decision in the batch',status='Exploratory after inspecting feasibility results; no untouched holdout or causal proof of profitability',code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (dest/'registration.json').write_text(json.dumps(registration,indent=2));decisions={};stats=[];failures=[]
    for start in range(0,len(packets),5):
        batch=packets[start:start+5]
        try:
            result,measurement=review(batch)
            for row in result:decisions[row['id']]={**row,'extra_delay':math.ceil(measurement['wall_seconds'])}
            stats.append(measurement)
        except Exception as exc:failures.append(dict(ids=[p['id'] for p in batch],error=str(exc)[:160]))
        (dest/'decisions.json').write_text(json.dumps(dict(decisions=decisions,stats=stats,failures=failures),indent=2))
    results=[]
    for kind in ['momentum','mean_reversion']:
        agent={mapping[k]['slug']:v['allow'] for k,v in decisions.items() if mapping[k]['strategy']==kind}
        delay={mapping[k]['slug']:v['extra_delay'] for k,v in decisions.items() if mapping[k]['strategy']==kind}
        rule={mapping[p['id']]['slug']:p['spread']<=.03 and .15<=(p['ask'] if p['side']=='long' else 1-p['bid'])<=.85 for p in packets if p['strategy']==kind}
        for name,allowed,lags in [('no_agent',None,None),('spread_rule',rule,None),('agent',agent,None),('agent_with_delay',agent,delay)]:
            result=replay(histories,cfg,kind,'0',allowed,lags);result['arm']=name;results.append(result)
    report=dict(created_at=time.time(),registration=registration,decisions=decisions,measurements=stats,failures=failures,results=results,conclusion='Exploratory comparison on a tiny selected sample. No US agent advantage or profitable strategy is established. Reduced losses through vetoes are not independent alpha evidence.',live_execution=False)
    (dest/'report.json').write_text(json.dumps(report,indent=2));pointer=ROOT/'data/us-agent-latest.json';tmp=pointer.with_suffix('.tmp');tmp.write_text(json.dumps({'directory':str(dest)}));tmp.replace(pointer)
    print(json.dumps(dict(directory=str(dest),packets=len(packets),decisions=len(decisions),failures=failures,measurements=stats,results=[{k:r[k] for k in ['strategy','arm','entries','exits','realized_pnl','open_basis']} for r in results])))

if __name__=='__main__':main()
