import unittest
from polylab.us_baskets import basket,snapshot,candidate

class USBasketTests(unittest.TestCase):
    def test_complete_payout_floor_does_not_apply_to_partial_legs(self):
        rules=[dict(slug=str(i)) for i in range(3)]
        quotes={str(i):dict(t=100,ask=p,bid=p-.01) for i,p in enumerate([.2,.3,.4])}
        result=basket(rules,quotes,'buy_complete_ladder','5','0')
        self.assertGreater(float(result['net_floor']),0)
        self.assertLess(float(result['partial_fill_worst_pnl']),-3)
        self.assertLessEqual(float(result['cost']),5)
        self.assertEqual(float(result['terminal_floor']),result['quantity'])
        shorts=basket(rules,{str(i):dict(t=100,bid=.5,ask=.51) for i in range(3)},'short_complete_ladder','5','0')
        self.assertGreater(float(shorts['net_floor']),0)
        self.assertEqual(float(shorts['terminal_floor']),shorts['quantity']*2)

    def test_coherent_snapshot_rejects_old_skewed_and_pre_delay_samples(self):
        rules=[dict(slug='a'),dict(slug='b')];histories={'a':[dict(t=100,bid=.2,ask=.3)],'b':[dict(t=115,bid=.3,ask=.4)]}
        self.assertIsNone(snapshot(rules,histories,120,60,10))
        self.assertIsNone(snapshot(rules,histories,200,60,20))
        self.assertIsNone(snapshot(rules,histories,120,60,20,after=101))
        self.assertIsNotNone(snapshot(rules,histories,120,60,20))

    def test_later_quote_must_retain_edge_and_all_legs_must_refresh(self):
        rules=[dict(slug='a'),dict(slug='b')]
        cfg=dict(decision_start_offset=0,decision_end_offset=0,decision_grid_seconds=60,max_quote_age_seconds=60,max_leg_skew_seconds=10,entry_budget='5',minimum_net_dollars='.1',entry_delay_seconds=60)
        histories={s:[dict(t=100,bid=.39,ask=.4),dict(t=160,bid=.59,ask=.6)] for s in ('a','b')}
        group=dict(rules=rules,histories=histories,target=100,date='2026-09-08')
        result,reasons,signals=candidate(group,'buy_complete_ladder',cfg,'0')
        self.assertIsNone(result);self.assertEqual(signals,1);self.assertEqual(reasons['floor_disappeared_before_entry'],1)
        for values in histories.values():values[1].update(bid=.39,ask=.4)
        result,_,_=candidate(group,'buy_complete_ladder',cfg,'0');self.assertEqual(result['entry_t'],160)
        histories['b'].pop();self.assertIsNone(candidate(group,'buy_complete_ladder',cfg,'0')[0])
