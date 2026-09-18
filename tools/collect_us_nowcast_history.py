"""Bounded history batches, paused around the registered forward entry window."""
import json,sys,time,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_marketdata import get,RateLimited

def main():
    import msvcrt
    root=Path(sys.argv[1]).resolve();cfg=json.loads((root/'registration.json').read_text());policy=cfg['collection_policy']
    with (root/'collector.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):lock.write(b'0');lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:print('duplicate_noop',flush=True);return
        try:
            for name,sha in json.loads((root/'code-freeze.json').read_text())['sha256'].items():
                if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen input changed '+name)
            for batch in range(policy['max_batches']):
                if time.time()>=policy['stop_at']:break
                while policy['blackout_start']<=time.time()<=policy['blackout_end']:time.sleep(10)
                deadline=time.monotonic()+235;errors=[];status='complete'
                for g in cfg['groups']:
                    for r in g['rules']:
                        out=root/(r['market_id']+'-history.json')
                        if out.exists():continue
                        if time.monotonic()>deadline or time.time()>=policy['stop_at'] or policy['blackout_start']<=time.time()<=policy['blackout_end']:status='partial';break
                        try:
                            raw,receipt=get('/v1/price-history',{'symbol':r['slug'],'timestamp.startTimestamp':g['target']-1800,'timestamp.endTimestamp':g['target']+2700,'fidelity':1})
                            out.write_text(json.dumps(dict(response=raw,receipt=receipt)),encoding='utf-8')
                        except Exception as exc:errors.append(dict(slug=r['slug'],error=str(exc)[:200]));status='partial';break
                    if status!='complete':break
                report=dict(status=status,batch=batch,updated_at=time.time(),files=len(list(root.glob('*-history.json'))),expected=sum(len(g['rules']) for g in cfg['groups']),errors=errors)
                (root/'collection.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
                if status=='complete':break
                time.sleep(30 if not errors else 300)
        finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

if __name__=='__main__':main()
