import unittest
import tempfile,json,threading
from pathlib import Path
from unittest.mock import patch
from polylab.us_scope import restrict_catalog
from polylab.us_marketdata import get,normalize_book,RateLimited,collect

class USScopeTests(unittest.TestCase):
    def test_international_mechanisms_are_excluded(self):
        rows=[{'id':x} for x in ['split-merge-redemption-arbitrage-ctf','momentum-trend-following','automated-uma-dispute-risk-forecaster','weather-event-markets']]
        self.assertEqual([r['id'] for r in restrict_catalog(rows)],['momentum-trend-following','weather-event-markets'])
        self.assertEqual([r['status'] for r in restrict_catalog(rows)],['US feasibility + forward paper','US CLI forecast component'])
    def test_client_cannot_request_orders_or_external_hosts(self):
        for path in ['/v1/orders','https://clob.polymarket.com/book','/v1/markets/../orders','/v1/markets/a/book?host=other']:
            with self.assertRaises(ValueError):get(path)
    def test_us_book_preserves_usd_whole_contracts_and_identity(self):
        raw={'marketData':{'marketSlug':'test','bids':[{'px':{'value':'.45','currency':'USD'},'qty':'10.0000'}],'offers':[{'px':{'value':'.46','currency':'USD'},'qty':'20'}],'state':'MARKET_STATE_OPEN','transactTime':'2026-09-17T12:00:00.123456789Z'}}
        result=normalize_book(raw,'test');self.assertTrue(result['valid']);self.assertEqual(result['bids'],[[.45,10]])
        with self.assertRaises(ValueError):normalize_book(raw,'wrong')
        raw['marketData']['bids'][0]['qty']='1.5'
        result=normalize_book(raw,'test')
        self.assertEqual(result['bids'],[[.45,1.5]])
        self.assertTrue(result['fractional_depth_observed'])
        self.assertFalse(result['execution_eligible'])
    def test_rate_limit_preserves_long_retry_after(self):
        self.assertEqual(RateLimited('900').retry_after,900)
        self.assertEqual(RateLimited(None).retry_after,300)
    def test_rate_limit_stops_batch_and_persists_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp, patch('polylab.us_marketdata.ROOT',Path(tmp)), patch('polylab.us_marketdata.get',side_effect=RateLimited('900')) as fetch:
            result=collect()
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(result['books'],[])
            cursor=json.loads((Path(tmp)/'data/us/discovery-cursor.json').read_text())
            self.assertGreater(cursor['resume_after'],result['created_at']+890)
            collect()
            self.assertEqual(fetch.call_count,1)
    def test_discovery_resumes_saved_offset(self):
        with tempfile.TemporaryDirectory() as tmp, patch('polylab.us_marketdata.ROOT',Path(tmp)), patch('polylab.us_marketdata.get',return_value=({'markets':[]},{})) as fetch:
            root=Path(tmp)/'data/us';root.mkdir(parents=True)
            (root/'discovery-cursor.json').write_text(json.dumps({'offset':800}))
            stop=threading.Event()
            with patch.object(stop,'wait',return_value=False):result=collect(stop)
            self.assertEqual(fetch.call_args.args[1]['offset'],800)
            self.assertTrue(result['pagination_reached_end'])
            self.assertFalse(result['discovery_complete'])
            self.assertEqual(result['next_offset'],0)

if __name__=='__main__':unittest.main()
