"""Apply source-reviewed NOAA viewer conventions without silently assuming them."""
import json,hashlib
from pathlib import Path
from .research import ROOT

def apply_review(rule,asof):
    path=ROOT/'data/rule-evidence/viewer-review.json'
    if not path.exists():return rule
    review=json.loads(path.read_text(encoding='utf-8'))
    if not 0<=asof-review['available_at']<=review['expires_after_seconds']:return rule
    if hashlib.sha256(Path(review['path']).read_bytes()).hexdigest()!=review['sha256']:raise ValueError('Reviewed viewer source hash mismatch')
    result={**rule,'rounding':review['rounding'],'rounding_verified':True,'viewer_evidence':dict(source=review['source_url'],sha256=review['sha256'],available_at=review['available_at'])}
    if rule['sampling']=='hourly':result['sampling_definition']=review['hourly_viewer_asos_filter']
    station=review['stations'].get(rule['station'])
    if station:
        if hashlib.sha256(Path(station['path']).read_bytes()).hexdigest()!=station['sha256']:raise ValueError('Station timezone source hash mismatch')
        result.update(timezone=station['timezone'],timezone_verified=True,timezone_evidence=station)
    return result
