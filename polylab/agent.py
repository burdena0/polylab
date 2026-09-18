"""Local LLM veto agent. It receives only a timestamp-safe numerical packet."""
import json,time,hashlib
from pathlib import Path
import requests
from .research import ROOT, prepare_models, packet
MODEL='qwen3.5:9b'
PROMPT=('You review anonymous historical prediction-market candidate entries for a research simulation. '
 'No real orders are possible. You may allow or veto the existing signal; never invent data. '
 'Consider predicted probability versus ask price, spread, liquidity and contradictory momentum. '
 'Quotes are cached with unknown exchange freshness in BOTH treatment arms; this experiment studies '
 'incremental signal filtering conditional on that shared limitation, not execution approval. '
 'Do not use outside knowledge or assume future prices. Return one decision per supplied id with '
 'allow boolean and a short factual reason (maximum 12 words). Preserve ids exactly.')

def review(packets,model=MODEL):
    schema={'type':'object','properties':{'decisions':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string'},'allow':{'type':'boolean'},'reason':{'type':'string'}},'required':['id','allow','reason'],'additionalProperties':False}}},'required':['decisions'],'additionalProperties':False}
    payload=dict(model=model,messages=[{'role':'system','content':PROMPT},{'role':'user','content':json.dumps(packets,allow_nan=False)}],think=False,stream=False,format=schema,keep_alive='10m',options={'temperature':0,'seed':731,'num_ctx':4096,'num_predict':768})
    start=time.monotonic();r=requests.post('http://127.0.0.1:11434/api/chat',json=payload,timeout=150);r.raise_for_status();raw=r.json();elapsed=time.monotonic()-start
    result=json.loads(raw['message']['content']);decisions=result.get('decisions',[])
    expected={p['id'] for p in packets}
    if len(decisions)!=len(expected) or {d.get('id') for d in decisions}!=expected or any(type(d.get('allow')) is not bool for d in decisions):raise ValueError('Invalid agent decision schema')
    return decisions,dict(wall_seconds=elapsed,prompt_tokens=raw.get('prompt_eval_count'),output_tokens=raw.get('eval_count'),load_seconds=raw.get('load_duration',0)/1e9,generation_seconds=raw.get('eval_duration',0)/1e9)

def compare(strategy='benter'):
    path=ROOT/'data'/'prepared'/'history.json';raw=path.read_bytes();history=json.loads(raw);model,_,_,test=prepare_models(history)
    # Fixed first 60 test markets. No selection by outcome, signal strength, or return.
    indices=list(range(min(60,len(test))));output=ROOT/'data'/('agent-comparison.json' if strategy=='benter' else 'agent-comparison-momentum.json')
    state=dict(model=MODEL,strategy=strategy,history_sha256=hashlib.sha256(raw).hexdigest(),prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),test_indices=indices,decisions={},failures=[],batches=[],started_at=time.time(),status='running')
    if output.exists():
        old=json.loads(output.read_text())
        if old.get('history_sha256')==state['history_sha256'] and old.get('model')==MODEL and old.get('prompt_sha256')==state['prompt_sha256']:state=old
    for start in range(0,len(indices),5):
        batch=[i for i in indices[start:start+5] if str(i) not in state['decisions']]
        if not batch:continue
        packets=[dict(id=str(i),**packet(test[i],model,strategy)) for i in batch]
        try:
            result,stats=review(packets)
            for d in result:state['decisions'][d['id']]={**d,'latency_seconds':stats['wall_seconds']}
            state['batches'].append(dict(ids=batch,**stats))
        except Exception as exc:
            state['failures'].append(dict(ids=batch,error=type(exc).__name__))
        output.write_text(json.dumps(state,indent=2),encoding='utf-8')
        print(f'Agent reviewed {len(state["decisions"])}/{len(indices)}',flush=True)
    state['status']='complete' if len(state['decisions'])==len(indices) else 'partial';state['finished_at']=time.time()
    output.write_text(json.dumps(state,indent=2),encoding='utf-8')
    return state

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--strategy',default='benter',choices=['benter','momentum-trend-following']);args=parser.parse_args();compare(args.strategy)
