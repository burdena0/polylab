import unittest
from copy import deepcopy
from tools.probe_us_forward_depth import assess

class USForwardDepthTests(unittest.TestCase):
    def test_cache_age_unknown_and_old_exchange_timestamp_remain_distinct(self):
        rules=[dict(slug='a'),dict(slug='b')]
        records=[dict(book=dict(slug=s,valid=True,state='MARKET_STATE_OPEN',bids=[[p-.01,100]],offers=[[p+.01,100]],exchange_at=100),receipt=dict(received_at=1000,round_trip_seconds=.1,public_cache_headers={'Age':'10','Date':'Thu, 01 Jan 1970 00:16:40 GMT'})) for s,p in [('a',.8),('b',.2)]]
        result=assess(rules,records,1.37)
        self.assertTrue(result['cache_qualified']);self.assertFalse(result['strict_five_second_ladder'])
        bad=deepcopy(records);del bad[0]['receipt']['public_cache_headers']['Age']
        self.assertFalse(assess(rules,bad,1.37)['cache_qualified'])
        bad[0]['book']['exchange_at']=None
        self.assertFalse(assess(rules,bad,1.37)['strict_five_second_ladder'])
        bad=deepcopy(records);bad[0]['book']['offers'][0][1]=.5;bad[1]['book']['bids'][0][1]=.5
        self.assertTrue(all(c['quantity']<=25 for c in assess(rules,bad,1.37)['candidates']))
