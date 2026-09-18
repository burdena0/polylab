import unittest
from polylab.us_replay import normalize_history,opportunity,replay

CFG=dict(start=0,end=4000,lookback_seconds=900,minimum_move='.02',entry_delay_seconds=60,hold_seconds=1800,max_next_quote_gap_seconds=300,entry_budget='5',capital='50',reserve='40')
class USReplayTests(unittest.TestCase):
    def test_display_prices_preserve_spread_and_reject_conflicts(self):
        rows=[dict(timestamp=1,longPrice=.6,shortPrice=.5),dict(timestamp=2,longPrice=.6,shortPrice=.5),dict(timestamp=2,longPrice=.7,shortPrice=.5),dict(timestamp=3,longPrice=.3,shortPrice=.5)]
        points,bad=normalize_history({'history':rows},0,4)
        self.assertEqual(len(points),1);self.assertEqual(points[0]['bid'],.5);self.assertEqual(points[0]['ask'],.6)
        self.assertEqual(bad['conflicting_timestamps'],1)
    def test_delay_and_future_prices_cannot_change_signal(self):
        points=[dict(t=t,bid=b,ask=b+.02,mid=b+.01) for t,b in [(0,.4),(900,.45),(960,.5),(2760,.55)]]
        o=opportunity(points,CFG,'momentum')
        self.assertEqual(o['signal_t'],900);self.assertEqual(o['entry']['t'],960);self.assertEqual(o['side'],'long')
        points[-1]['mid']=.01
        self.assertEqual(opportunity(points,CFG,'momentum')['signal_t'],900)
    def test_missing_exit_remains_open_and_cash_reconciles(self):
        points=[dict(t=t,bid=b,ask=b+.02,mid=b+.01) for t,b in [(0,.4),(900,.45),(960,.5)]]
        r=replay({'a':points},CFG,'momentum','0')
        self.assertEqual(r['entries'],1);self.assertEqual(r['exits'],0);self.assertEqual(r['positions'],1)
        self.assertEqual(float(r['realized_pnl']),0);self.assertLess(r['liquidation_floor_pnl'],0)
    def test_short_prices_and_shared_reserve(self):
        points=[dict(t=t,bid=b,ask=b+.02,mid=b+.01) for t,b in [(0,.6),(900,.5),(960,.5),(2760,.4)]]
        r=replay({str(i):points for i in range(8)},CFG,'momentum','0')
        # Two near-$5 entries leave enough reserve headroom for one smaller lot.
        self.assertEqual(r['entries'],3);self.assertEqual(r['exits'],3)
        self.assertTrue(all(float(x['cash'])>=40 for x in r['ledger'] if x['kind']=='buy'))
        self.assertGreater(float(r['realized_pnl']),0);self.assertGreaterEqual(float(r['cash']),40)
    def test_agent_delay_preserves_reviewed_signal_and_blocks_missing_decision(self):
        points=[dict(t=t,bid=b,ask=b+.02,mid=b+.01) for t,b in [(0,.4),(900,.45),(960,.5),(970,.6),(2770,.7)]]
        r=replay({'a':points},CFG,'momentum','0',{'a':True},{'a':10})
        self.assertEqual(r['ledger'][0]['t'],970);self.assertEqual(r['ledger'][0]['signal_t'],900)
        self.assertEqual(replay({'a':points},CFG,'momentum','0',{})['entries'],0)
