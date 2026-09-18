import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from polylab.paper_cohort import PaperCohort

class CohortTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.patches=[patch('polylab.paper.ROOT',root),patch('polylab.paper_cohort.ROOT',root)]
        for p in self.patches:p.start()
        self.c=PaperCohort()
    def tearDown(self):
        for p in self.patches:p.stop()
        self.temp.cleanup()
    def test_identical_feed_independent_budgets_and_delayed_entries(self):
        ticks=[]
        for i in range(62):
            mid=.2+min(i,60)*.01;ticks.append(dict(t=1000+i,bu=mid-.005,au=mid+.005,bd=1-mid-.005,ad=1-mid+.005,su=20,sau=100,sd=100,sad=100))
        market=dict(condition='test',start=1000,end=1300,min_shares=1,ticks=ticks,fee_schedule=dict(condition='test',received_at=1000,rate=.07,exponent=1,taker_only=True))
        self.c.ingest(market,ticks[60]);self.assertTrue(all(not a.state['positions'] for a in self.c.accounts))
        self.c.ingest(market,ticks[61]);base,limited=self.c.snapshots()
        self.assertEqual(base['last_shared_observation'],limited['last_shared_observation']);self.assertEqual(base['snapshots'],limited['snapshots'])
        self.assertGreater(base['positions'][0]['quantity'],limited['positions'][0]['quantity']);self.assertNotEqual(base['account_id'],limited['account_id'])
        for a in self.c.accounts:self.assertTrue((a.path.parent/'trades.jsonl').exists())

    def test_account_failure_stops_both_arms_and_records_coverage_break(self):
        market={'condition':'test'};tick={'t':1060}
        with patch.object(self.c.accounts[0],'step',side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):self.c.ingest(market,tick)
        self.assertTrue(self.c.stop_event.is_set())
        self.assertTrue(all(a.state['coverage_failure_at']==1060 for a in self.c.accounts))

if __name__=='__main__':unittest.main()
