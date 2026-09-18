"""Register a fixed unused-market test, then collect bounded public verification.

Never overwrites the original 600-market experiment or an existing study history.
"""
import sys,json,hashlib,time,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests,numpy as np,pyarrow as pa,pyarrow.compute as pc,pyarrow.parquet as pq
from polylab.research import ROOT,prepare_models

def main():
    dest=ROOT/'data'/'profit-study-v1';dest.mkdir(exist_ok=True);old=json.loads((ROOT/'data/prepared/history.json').read_text())
    if (dest/'history.json').exists():print('Frozen study history already exists; no overwrite.');return
    source=pq.read_table(ROOT/'data/btc/btc_markets.parquet').sort_by([('market_start','ascending'),('condition_id','ascending')]).to_pylist()
    lookup={m['condition_id']:m for m in source};registration=dest/'registration.json'
    if not registration.exists():
        model,_,_,_=prepare_models(old);seen={m['condition'] for m in old['markets']};eligible=[m for m in source if m['market_start'].timestamp()>=model['test_start'] and m['condition_id'] not in seen]
        selected=[eligible[i]['condition_id'] for i in np.linspace(0,len(eligible)-1,min(1200,len(eligible)),dtype=int)]
        hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'polylab/risk.py',ROOT/'polylab/risk_replay.py']}
        registration.write_text(json.dumps(dict(created_at=time.time(),objective='Net P&L after costs; no win-rate optimization',selection='1200 evenly spaced, previously unused condition IDs in the existing test calendar period',conditions=selected,source_revision=old['source']['revision'],code_hashes=hashes,primary_comparison=['baseline','liquidity'],secondary=['kelly_half','volatility','drawdown','combined'],parameters=dict(capital=50,kelly=.1,exposure=.15,fee_bps=100,slippage=.001,liquidity_participation=.1,liquidity_band=.03),caveat='Unused market rows in a previously examined calendar period, not an independent market regime.'),indent=2))
    reg=json.loads(registration.read_text());chosen=[lookup[c] for c in reg['conditions']];receipts=dest/'resolutions';receipts.mkdir(exist_ok=True)
    def verify(m):
        cid=m['condition_id'];path=receipts/(cid+'.json')
        try:
            if path.exists():d=json.loads(path.read_text())
            else:
                for attempt in range(2):
                    response=requests.get('https://clob.polymarket.com/markets/'+cid,timeout=8)
                    if response.ok:break
                    if response.status_code in [404,400]:break
                    time.sleep(1+attempt)
                response.raise_for_status();d=response.json();path.write_text(json.dumps(d))
            if d['condition_id']!=cid or not d['closed'] or d['market_slug']!=m['slug']:raise ValueError('Identity/status mismatch')
            mapping={t['outcome'].lower():t for t in d['tokens']}
            if mapping['up']['token_id']!=m['token_up'] or mapping['down']['token_id']!=m['token_down'] or sum(t.get('winner') is True for t in d['tokens'])!=1:raise ValueError('Token/outcome mismatch')
            return dict(condition=cid,slug=m['slug'],start=m['market_start'].timestamp(),end=m['market_end'].timestamp(),up=m['token_up'],down=m['token_down'],min_shares=float(d['minimum_order_size']),label=int(mapping['up']['winner']),label_used_for_signal=False,resolution_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        except Exception as exc:return dict(condition=cid,error=type(exc).__name__)
    records=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(verify,m) for m in chosen]
        for future in as_completed(futures):
            records.append(future.result())
            if len(records)%100==0:
                progress=dict(pid=os.getpid(),done=len(records),selected=len(chosen),failed=sum('error' in r for r in records),updated_at=time.time())
                (dest/'progress.json').write_text(json.dumps(progress));print(json.dumps(progress),flush=True)
    valid={r['condition']:r for r in records if 'error' not in r};groups={cid:[] for cid in valid};values=pa.array(list(valid))
    for batch in pq.ParquetFile(ROOT/'data/btc/btc_ticks.parquet').iter_batches(batch_size=65536):
        batch=batch.filter(pc.is_in(batch.column('condition_id'),value_set=values))
        for row in batch.select(['condition_id','t','bu','au','bd','ad','su','sd','sau','sad']).to_pylist():
            cid=row.pop('condition_id');m=valid[cid]
            if m['start']<=row['t']<m['end']:groups[cid].append({k:v if v is not None and np.isfinite(v) else None for k,v in row.items()})
    for cid,m in valid.items():
        m['ticks']=sorted(groups[cid],key=lambda t:t['t'])
        if len({t['t'] for t in m['ticks']})!=len(m['ticks']):raise ValueError('Duplicate source time')
    doc=dict(markets=sorted(valid.values(),key=lambda m:m['start']),failed=[r for r in records if 'error' in r],registration=reg,source=old['source'],created_at=time.time())
    tmp=dest/'history.tmp';tmp.write_text(json.dumps(doc,allow_nan=False));tmp.replace(dest/'history.json')
    print(json.dumps(dict(complete=True,verified=len(valid),failed=len(doc['failed']),ticks=sum(len(m['ticks']) for m in valid.values()))),flush=True)
if __name__=='__main__':main()
