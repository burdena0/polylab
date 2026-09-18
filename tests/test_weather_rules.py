import json,tempfile,unittest,hashlib
from pathlib import Path
from unittest.mock import patch
from polylab.weather_rules import apply_review

class RuleEvidenceTests(unittest.TestCase):
    def test_review_is_time_bounded_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as d,patch('polylab.weather_rules.ROOT',Path(d)):
            root=Path(d)/'data/rule-evidence';root.mkdir(parents=True);source=root/'viewer.js';source.write_bytes(b'reviewed fixture')
            review=dict(available_at=1000,expires_after_seconds=86400,path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_url='https://www.weather.gov/source/wrh/timeseries/obs.js',rounding='nearest_half_up',hourly_viewer_asos_filter='source filter',stations={})
            (root/'viewer-review.json').write_text(json.dumps(review));rule=dict(station='EGLC',sampling='all_readings',rounding_verified=False,timezone_verified=False)
            self.assertTrue(apply_review(rule,1001)['rounding_verified']);self.assertFalse(apply_review(rule,999)['rounding_verified']);self.assertFalse(apply_review(rule,90000)['rounding_verified'])
            source.write_bytes(b'changed')
            with self.assertRaises(ValueError):apply_review(rule,1001)

if __name__=='__main__':unittest.main()
