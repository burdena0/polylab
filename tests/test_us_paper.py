import unittest
from polylab.us_paper import Engine

def book(t,bid=.4,ask=.42,depth=100,age=0):
    return dict(slug='a',received_at=t,exchange_at=t-age,valid=True,state='MARKET_STATE_OPEN',bids=[[bid,depth]],offers=[[ask,depth]])

class USPaperTests(unittest.TestCase):
    def test_forward_delay_no_retroactive_fill_and_restore(self):
        e=Engine();e.observe(book(0),10000);e.observe(book(900,.45,.47),10000)
        self.assertTrue(e.pending);self.assertFalse(e.accounts['momentum'].positions)
        e.observe(book(901,.45,.47),10000);self.assertFalse(e.accounts['momentum'].positions)
        e=Engine(e.dump());e.observe(book(940,.45,.47),10000)
        self.assertTrue(e.accounts['momentum'].positions)
        e.observe(book(2740,.6,.62),10000)
        self.assertFalse(e.accounts['momentum'].positions)
        self.assertGreater(e.accounts['momentum'].realized,0)
        self.assertLess(e.accounts['mean_reversion'].realized,0)
        self.assertEqual(Engine(e.dump()).dump(),e.dump())
    def test_stale_book_does_not_signal_or_fill(self):
        e=Engine();e.observe(book(0,age=6),10000)
        self.assertEqual(e.processed,0);self.assertEqual(e.rejected,1)
        e.observe(book(0),10000);e.observe(book(900,.45,.47),10000)
        e.observe(book(940,.45,.47,age=10),10000)
        self.assertFalse(e.accounts['momentum'].positions)
    def test_depth_floor_and_verified_nonbinary_settlement(self):
        e=Engine();e.observe(book(0),10000);e.observe(book(900,.45,.47),10000)
        e.observe(book(940,.45,.47,depth=7.9),10000)
        self.assertEqual(e.accounts['momentum'].positions['a']['quantity'],1)
        e.settle('a','.5',3000)
        self.assertEqual(e.accounts['momentum'].snapshot()['positions'],0)
        with self.assertRaises(ValueError):e.settle('a','NaN',3000)
    def test_expired_signal_cannot_fill_from_late_book(self):
        e=Engine();e.observe(book(0),10000);e.observe(book(900,.45,.47),10000)
        e.observe(book(1100,.45,.47),10000)
        self.assertFalse(e.accounts['momentum'].positions)
