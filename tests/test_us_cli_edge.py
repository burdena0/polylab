import unittest
from polylab.us_cli_edge import latest_cli,conditional_direction,assess_quote

class CLIEdgeTests(unittest.TestCase):
    def sample(self):
        rule=dict(slug='x',station='KNYC',date='2026-09-17',metric='max',standard_utc_offset=-5,lower=80,upper=81)
        obs=dict(station='KNYC',date='2026-09-17',issued_at=1789675000,available_at=1789675100,max_f=82,min_f=65,complete_day=False,source_sha256='abc')
        return rule,obs,1789675200

    def test_interim_only_excludes_strictly_lower_band(self):
        rule,obs,now=self.sample()
        self.assertEqual(conditional_direction(rule,obs,now)['side'],'short')
        self.assertIsNone(conditional_direction({**rule,'upper':82},obs,now))
        self.assertIsNone(conditional_direction({**rule,'lower':83,'upper':84},obs,now))

    def test_tail_and_minimum_bounds(self):
        rule,obs,now=self.sample()
        self.assertEqual(conditional_direction({**rule,'upper':None},obs,now)['side'],'long')
        self.assertEqual(conditional_direction({**rule,'metric':'min'},obs,now)['side'],'short')
        self.assertEqual(conditional_direction({**rule,'metric':'min','lower':None,'upper':65},obs,now)['side'],'long')

    def test_complete_day_classifies_each_band(self):
        rule,obs,now=self.sample();obs['complete_day']=True
        self.assertEqual(conditional_direction({**rule,'upper':82},obs,now)['side'],'long')

    def test_receipt_time_prevents_archive_lookahead(self):
        rule,obs,now=self.sample()
        self.assertIsNone(latest_cli([obs],'KNYC',rule['date'],obs['available_at']-1))
        with self.assertRaises(ValueError):conditional_direction(rule,obs,obs['available_at']-1)

    def test_same_time_conflicts_fail_closed_and_later_revision_wins(self):
        rule,obs,now=self.sample();other={**obs,'max_f':79,'source_sha256':'changed','available_at':obs['available_at']+1}
        with self.assertRaises(ValueError):latest_cli([obs,other],'KNYC',rule['date'],now)
        other['issued_at']+=1
        latest=latest_cli([obs,other],'KNYC',rule['date'],now)
        self.assertIsNone(conditional_direction(rule,latest,now))

    def test_stale_quote_has_no_qualified_signal_or_profit(self):
        rule,obs,now=self.sample();signal=conditional_direction(rule,obs,now)
        book=dict(slug='x',valid=True,state='MARKET_STATE_OPEN',exchange_at=now-90,bids=[[.2,100]],offers=[[.3,100]])
        receipt=dict(requested_at=now,received_at=now+1,round_trip_seconds=1,public_cache_headers={'Date':'Thu, 17 Sep 2026 17:20:00 GMT','Age':'0'})
        cfg=dict(max_http_age_seconds=45,max_exchange_age_seconds=5,slippage_per_side='.005',entry_budget='5',depth_fraction='.25',minimum_conditional_margin='.10')
        result=assess_quote(signal,book,receipt,cfg)
        self.assertFalse(result['research_qualified']);self.assertIsNone(result['profit']);self.assertEqual(result['positions_opened'],0)
        receipt['requested_at']=obs['available_at']-1
        with self.assertRaises(ValueError):assess_quote(signal,book,receipt,cfg)

if __name__=='__main__':unittest.main()
