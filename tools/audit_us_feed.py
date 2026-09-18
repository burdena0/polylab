"""Read-only explanation of frozen paper-feed exclusions, preserving raw evidence."""
import sys,json,time,hashlib,statistics
from pathlib import Path
from collections import defaultdict,Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_marketdata import normalize_book

def main():
    source=ROOT/'data/us-paper-v1/observations.jsonl';raw=source.read_bytes()
    complete=raw[:raw.rfind(b'\n')+1];by_slug=defaultdict(list);reasons=Counter();skipped=0
    for line in complete.splitlines():
        doc=json.loads(line)
        if 'marketData' not in doc['raw']:skipped+=1;continue
        slug=doc['raw']['marketData']['marketSlug'];book=normalize_book(doc['raw'],slug);t=doc['receipt']['received_at'];age=t-book['exchange_at'] if book['exchange_at'] is not None else None
        reason='passes_initial_feed_gate'
        if book['state']!='MARKET_STATE_OPEN':reason='not_open'
        elif not book['valid']:reason='one_sided_or_crossed'
        elif age is None:reason='missing_exchange_timestamp'
        elif age<0:reason='future_exchange_timestamp'
        elif age>5:reason='exchange_timestamp_older_than_5_seconds'
        reasons[reason]+=1;by_slug[slug].append(dict(received_at=t,exchange_at=book['exchange_at'],age=age,state=book['state'],valid=book['valid'],bids=book['bids'],offers=book['offers'],reason=reason))
    groups=[]
    for slug,rows in by_slug.items():
        ages=[r['age'] for r in rows if r['state']=='MARKET_STATE_OPEN' and r['valid'] and r['age'] is not None];changes=0;same_stamp_changes=0
        for a,b in zip(rows,rows[1:]):
            if (a['bids'],a['offers'])!=(b['bids'],b['offers']):
                changes+=1;same_stamp_changes+=a['exchange_at']==b['exchange_at']
        groups.append(dict(slug=slug,receipts=len(rows),states=dict(Counter(r['state'] for r in rows)),reasons=dict(Counter(r['reason'] for r in rows)),distinct_exchange_timestamps=len({r['exchange_at'] for r in rows}),book_changes=changes,book_changes_with_unchanged_timestamp=same_stamp_changes,valid_open_age_min_seconds=min(ages) if ages else None,valid_open_age_median_seconds=statistics.median(ages) if ages else None,last_receipt=rows[-1]['received_at']))
    report=dict(created_at=time.time(),source=str(source),prefix_bytes=len(complete),prefix_sha256=hashlib.sha256(complete).hexdigest(),records=sum(len(r) for r in by_slug.values()),settlement_records_skipped=skipped,incomplete_tail_bytes=len(raw)-len(complete),reasons=dict(reasons),groups=groups,conclusion='Feed-gate diagnostics only. HTTP receipt age is not exchange freshness or fill evidence. No frozen experiment settings changed.',live_execution=False)
    dest=ROOT/'data/us-freshness'/str(time.time_ns());dest.mkdir(parents=True);(dest/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(directory=str(dest),**report),indent=2))

if __name__=='__main__':main()
