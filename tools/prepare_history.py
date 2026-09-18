"""Fixed chronological BTC sample with separately verified CLOB resolution records."""
import json, time, hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import requests
ROOT=Path(__file__).resolve().parents[1]

def main():
    src=ROOT/'data'/'btc'; out=ROOT/'data'/'prepared';out.mkdir(exist_ok=True)
    meta=pq.read_table(src/'btc_markets.parquet').sort_by([('market_start','ascending'),('condition_id','ascending')]).to_pylist()
    # Selection fixed by position and time, never return, volume or inferred label.
    chosen=[meta[i] for i in np.linspace(0,len(meta)-1,600,dtype=int)]
    ids={m['condition_id'] for m in chosen}
    (out/'registration.json').write_text(json.dumps(dict(created_at=time.time(),selection='600 evenly spaced chronological market indices across the full BTC archive',condition_ids=sorted(ids),split='60% fundamental fit / 20% combination fit / 20% evaluation; one-day embargo'),indent=2))
    receipts=out/'resolutions';receipts.mkdir(exist_ok=True)
    def verify(m):
        path=receipts/(m['condition_id']+'.json')
        try:
            if path.exists(): d=json.loads(path.read_text())
            else:
                for attempt in range(3):
                    r=requests.get('https://clob.polymarket.com/markets/'+m['condition_id'],timeout=12)
                    if r.ok:break
                    time.sleep(1+attempt)
                r.raise_for_status();d=r.json()
                path.write_text(json.dumps(d),encoding='utf-8')
            assert d['condition_id']==m['condition_id'] and d['closed'] is True and d['market_slug']==m['slug']
            mapping={t['outcome'].lower():t for t in d['tokens']}
            assert mapping['up']['token_id']==m['token_up'] and mapping['down']['token_id']==m['token_down']
            assert sum(t.get('winner') is True for t in d['tokens'])==1
            return dict(condition=m['condition_id'],slug=m['slug'],start=m['market_start'].timestamp(),end=m['market_end'].timestamp(),up=m['token_up'],down=m['token_down'],label=int(mapping['up']['winner']),label_source='CLOB closed market winner flag',min_shares=float(d['minimum_order_size']),resolution_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        except Exception as exc:
            return dict(condition=m['condition_id'],error=type(exc).__name__)
    with ThreadPoolExecutor(max_workers=3) as pool: markets=list(pool.map(verify,chosen))
    valid={m['condition']:m for m in markets if 'error' not in m}
    grouped={cid:[] for cid in valid}
    for batch in pq.ParquetFile(src/'btc_ticks.parquet').iter_batches(batch_size=65536):
        batch=batch.filter(pc.is_in(batch.column('condition_id'),value_set=pa.array(list(valid))))
        for row in batch.select(['condition_id','t','bu','au','bd','ad','su','sd','sau','sad']).to_pylist():
            cid=row.pop('condition_id');m=valid[cid]
            if m['start']<=row['t']<m['end']:
                grouped[cid].append({k:(v if v is not None and np.isfinite(v) else None) for k,v in row.items()})
    for cid,m in valid.items():
        rows=sorted(grouped[cid],key=lambda x:x['t']); times=[r['t'] for r in rows]
        if len(set(times))!=len(times):raise ValueError('Duplicate source times')
        m['ticks']=rows
    doc=dict(markets=list(valid.values()),failed=[m for m in markets if 'error' in m],source=json.loads((src/'receipt.json').read_text()),generated_at=time.time(),quote_freshness_verified=False,settlement_timing_verified=False)
    (out/'history.json').write_text(json.dumps(doc,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(verified=len(valid),failed=len(doc['failed']),ticks=sum(len(m['ticks']) for m in valid.values()))))
if __name__=='__main__':main()
