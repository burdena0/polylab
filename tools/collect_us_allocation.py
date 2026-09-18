"""Bounded common-time history collection, shared US throttle; no orders."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from polylab.us_marketdata import get, RateLimited

def main():
    root = Path(sys.argv[1]); cfg = json.loads((root/'registration.json').read_text())
    deadline = time.monotonic()+235
    errors = []
    status = 'complete'
    for g in cfg['groups']:
        for r in g['rules']:
            out = root/(r['market_id']+'-history.json')
            if out.exists(): continue
            if time.monotonic() >= deadline:
                status = 'partial_time_budget'; break
            try:
                raw, receipt = get('/v1/price-history', {'symbol':r['slug'], 'timestamp.startTimestamp':g['target']-1800, 'timestamp.endTimestamp':g['target']+2700, 'fidelity':1})
                out.write_text(json.dumps(dict(response=raw, receipt=receipt)), encoding='utf-8')
            except Exception as exc:
                errors.append(dict(slug=r['slug'], error=str(exc)[:180]))
                status = 'partial_cooldown' if isinstance(exc, RateLimited) else 'partial_error'
                break
        if status != 'complete': break
    report = dict(status=status, files=len(list(root.glob('*-history.json'))), expected=sum(len(g['rules']) for g in cfg['groups']), errors=errors, updated_at=time.time())
    (root/'collection.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)

if __name__ == '__main__': main()
