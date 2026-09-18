"""Audit completed prospective passes without changing a running collector."""
import json,sys,hashlib,time
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_weather import parse_cli
from polylab.us_marketdata import normalize_book
from polylab.us_cli_edge import assess_quote,conditional_direction

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    root=Path(sys.argv[1]).resolve();cfg=json.loads((root/'registration.json').read_text());checks=0
    def check(ok,message):
        nonlocal checks
        checks+=1
        if not ok:raise AssertionError(message)
    for name,sha in json.loads((root/'code-freeze.json').read_text())['sha256'].items():check(digest(ROOT/name)==sha,'Frozen code/input '+name)
    reports=sorted(root.glob('passes/*/report.json'));observations={};sources={};quotes=[];errors=[];counts=Counter();reasons=Counter();versions=[];missing_required_side=0
    for path in reports:
        sources[str(path.relative_to(root))]=digest(path);r=json.loads(path.read_text());counts[r['station']]+=1
        for receipt in r['receipts']:
            src=path.parent/receipt['file'];doc=json.loads(src.read_text());sources[str(src.relative_to(root))]=digest(src)
            check(json.loads(doc['raw_text'])==doc['response'],'Exact raw JSON contents')
            check(hashlib.sha256(doc['raw_text'].encode()).hexdigest()==receipt['sha256'],'Original NWS bytes')
            check(r['started_at']<=receipt['requested_at']<=receipt['received_at']<=r['completed_at'],'Local receipt chronology')
            if doc['response'].get('productCode')=='CLI':
                obs=parse_cli(doc['response'],r['station'],receipt['received_at']);key=(obs['station'],obs['date'],obs['source_sha256'])
                if key not in observations:observations[key]=obs
        for q in r['quotes']:
            src=path.parent/q['receipt_file'];doc=json.loads(src.read_text());sources[str(src.relative_to(root))]=digest(src)
            book=normalize_book(doc['response'],q['signal']['slug']);check(book==doc['book'],'Raw book identity and normalization')
            required=book['offers'] if q['signal']['side']=='long' else book['bids']
            missing_required_side+=int(not required)
            check(r['started_at']<=doc['receipt']['requested_at']<=doc['receipt']['received_at']<=r['completed_at'],'Book local chronology')
            signal=q['signal'];key=(signal['station'],signal['date'],signal['observation_sha256']);check(key in observations,'Observation exists before quote')
            obs=observations[key];check(obs['available_at']==signal['observation_available_at'],'First actual receipt retained')
            rule=next(r for r in cfg['rules'] if r['slug']==signal['slug']);expected=conditional_direction(rule,obs,doc['receipt']['received_at'])
            check(expected==signal,'CLI band logic')
            calculation=assess_quote(signal,book,doc['receipt'],cfg);check(calculation=={k:v for k,v in q.items() if k!='receipt_file'},'Quote/fee/freshness calculation')
            check(q['profit'] is None and q['positions_opened']==0,'No invented paper profit')
            quotes.append(q);reasons.update(q['reasons'])
        errors.extend(r['errors']);versions.extend(r['new_versions'])
    pairs=[]
    for q in quotes:
        earlier=[p for p in quotes if p['signal']['slug']==q['signal']['slug'] and p['signal']['observation_sha256']==q['signal']['observation_sha256'] and p['received_at']+60<=q['received_at']]
        if not earlier:continue
        previous=max(earlier,key=lambda p:p['received_at'])
        pairs.append(dict(slug=q['signal']['slug'],first=previous['received_at'],later=q['received_at'],both_qualified=bool(q.get('research_qualified') and previous.get('research_qualified')),earlier_price=previous.get('price'),later_price=q.get('price'),profit=None))
    result=dict(created_at=time.time(),status='passed',checks=checks,completed_passes=len(reports),passes_by_station=dict(counts),unique_cli_versions=len(observations),newly_observed_versions=versions,quotes=len(quotes),missing_required_side=missing_required_side,qualified_quotes=sum(bool(q.get('research_qualified')) for q in quotes),rejection_counts=dict(reasons),delayed_pairs=pairs,errors=errors,source_hashes=sources,positions=0,realized_profit=None,live_execution=False,collector_status='Not inferred from artifacts; verify process/session separately',limitations=cfg['limitations'])
    dest=root/('audit-'+str(time.time_ns()));dest.mkdir();(dest/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['source_hashes','newly_observed_versions','delayed_pairs','limitations']},indent=2));print(str(dest))

if __name__=='__main__':main()
