import unittest
from polylab.us_endgame import economics,screen

class EndgameTests(unittest.TestCase):
    def test_profit_includes_fee_and_full_loss(self):
        r=economics('.90',100,probability='.95')
        self.assertEqual(r['quantity'],5);self.assertEqual(r['cost'],'4.53')
        self.assertEqual(r['conditional_win_profit'],'0.47');self.assertEqual(r['expected_profit'],'0.22')
        self.assertEqual(r['loss_if_wrong'],'-4.53')
        self.assertEqual(r['perfect_repeated_wins_to_exceed_5'],11)
        self.assertEqual(economics('.99',100)['perfect_repeated_wins_to_exceed_5'],101)

    def test_budget_depth_and_slippage(self):
        self.assertEqual(economics('.50',3)['quantity'],0)
        r=economics('.99',100,slippage='.005')
        self.assertEqual(r['conditional_win_profit'],'0.025')
        self.assertEqual(economics('.50',100,budget='.50')['quantity'],0)
        with self.assertRaises(ValueError):economics('.99',100,slippage='.02')

    def inputs(self):
        return (dict(slug='example',observation_issued_at=90,observation_available_at=95,complete_day=True,side='long'),
            dict(slug='example',exchange_at=99,state='MARKET_STATE_OPEN',bids=[],offers=[[.90,100]],valid=False),
            dict(requested_at=99,received_at=100,round_trip_seconds=1,public_cache_headers={'Date':'Thu, 01 Jan 1970 00:01:39 GMT','Age':'0'}),
            dict(max_exchange_age_seconds=5,max_http_age_seconds=45,entry_budget='5',slippage_per_side='0',depth_fraction='.25',minimum_conditional_margin='.1'))

    def test_needed_side_only_not_opposite_side(self):
        s,b,r,c=self.inputs();x=screen(s,b,r,c)
        self.assertTrue(x['research_qualified']);self.assertIsNone(x['expected_profit']);self.assertEqual(x['positions_opened'],0)
        s['side']='short';self.assertFalse(screen(s,b,r,c)['research_qualified'])

    def test_no_closed_market_stale_or_future_information(self):
        s,b,r,c=self.inputs();b['state']='MARKET_STATE_CLOSED'
        self.assertFalse(screen(s,b,r,c)['research_qualified'])
        s,b,r,c=self.inputs();b['exchange_at']=10
        self.assertFalse(screen(s,b,r,c)['research_qualified'])
        s,b,r,c=self.inputs();s['observation_available_at']=100
        with self.assertRaises(ValueError):screen(s,b,r,c)
        s,b,r,c=self.inputs();s['complete_day']=False
        self.assertFalse(screen(s,b,r,c)['research_qualified'])
