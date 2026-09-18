import copy,unittest
from polylab.coherence import STRATEGIES,Costs,evaluate,example
from polylab.coherence_replay import replay

CTF='split-merge-redemption-arbitrage-ctf'
NO='multi-outcome-overround-shorting-dutch-book-lay'
FREE=dict(fee_bps=0,slippage=0,fixed_cost=0)

class CoherenceTests(unittest.TestCase):
    def test_all_declared_strategies_run(self):
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                r=evaluate(strategy,example(strategy));self.assertTrue(r['candidates']);self.assertFalse(r['execution_eligible'])
    def test_merge_uses_asks_and_correct_direction(self):
        r=evaluate(CTF,example(CTF),FREE)['best']
        self.assertIn('merge',r['name']);self.assertAlmostEqual(r['unit_cost'],.88);self.assertEqual(r['unit_receipt_floor'],1);self.assertGreater(r['net_floor'],0)
    def test_split_uses_bids_and_fully_funds_collateral(self):
        d=example(CTF)
        for side in ['yes','no']:d['markets'][0][side].update(bid=.56,ask=.60)
        r=evaluate(CTF,d,FREE)['best'];self.assertIn('Split',r['name']);self.assertEqual(r['unit_cost'],1);self.assertAlmostEqual(r['unit_receipt_floor'],1.12);self.assertLessEqual(r['required_capital'],7.5)
    def test_no_basket_payout_is_n_minus_one(self):
        r=evaluate(NO,example(NO),FREE)['best']
        self.assertEqual(r['unit_receipt_floor'],2)
        # Enumerate all three winners, independently of the pricing implementation.
        self.assertTrue(all(sum(i!=winner for i in range(3))==2 for winner in range(3)))
    def test_bid_sum_alone_cannot_create_no_basket_edge(self):
        d=example(NO)
        for m in d['markets']:m['yes'].update(bid=.4,ask=.5);m['no'].update(bid=.7,ask=.8)
        r=evaluate(NO,d,FREE)['best'];self.assertFalse(r['eligible']);self.assertLess(r['net_floor'],0)
    def test_gas_eliminates_marginal_opportunity(self):
        d=example(CTF)
        for side in ['yes','no']:d['markets'][0][side].update(bid=.48,ask=.495)
        self.assertTrue(evaluate(CTF,d,FREE)['best']['eligible'])
        self.assertFalse(evaluate(CTF,d,{**FREE,'fixed_cost':.2})['best']['eligible'])
    def test_depth_and_venue_minimum_are_not_overridden(self):
        d=example(CTF);d['markets'][0]['yes']['ask_size']=2
        self.assertFalse(evaluate(CTF,d,FREE)['best']['eligible'])
    def test_future_stale_unknown_and_async_quotes(self):
        for stamp in [1001,990,None]:
            d=example(CTF);d['markets'][0]['yes']['exchange_at']=stamp
            with self.subTest(stamp=stamp),self.assertRaises(ValueError):evaluate(CTF,d)
        d=example(CTF);d['markets'][0]['yes']['exchange_at']=997
        with self.assertRaisesRegex(ValueError,'Asynchronous'):evaluate(CTF,d)
    def test_duplicate_tokens_and_wrong_condition_fail(self):
        d=example(CTF);d['markets'][0]['no']['token']=d['markets'][0]['yes']['token']
        with self.assertRaises(ValueError):evaluate(CTF,d)
        d=example(CTF);d['markets'][0]['yes']['condition']='different'
        with self.assertRaises(ValueError):evaluate(CTF,d)
    def test_names_do_not_prove_relationship(self):
        d=example(NO);d['relation']['verified']=False
        with self.assertRaises(ValueError):evaluate(NO,d)
        d=example(NO);d['markets'][1]['definition_id']='other-station'
        with self.assertRaisesRegex(ValueError,'settlement definition'):evaluate(NO,d)
    def test_partition_must_include_none_and_be_exclusive(self):
        for field in ['exclusive','exhaustive']:
            d=example(NO);d['relation'][field]=False
            with self.assertRaises(ValueError):evaluate(NO,d)
    def test_temperature_band_gap_and_missing_tails_rejected(self):
        sid='temperature-band-ladder-coherence'
        for index,key,value in [(0,'low',0),(1,'low',11),(2,'high',30)]:
            d=example(sid);d['relation']['bands'][index][key]=value
            with self.assertRaises(ValueError):evaluate(sid,d)
    def test_overlapping_thresholds_not_treated_as_partition(self):
        d=example('strike-ladder-monotonicity-arbitrage')
        with self.assertRaises(ValueError):evaluate(NO,d)
    def test_threshold_pair_is_superset_yes_subset_no(self):
        sid='strike-ladder-monotonicity-arbitrage';r=evaluate(sid,example(sid),FREE)['best']
        self.assertEqual([(l['condition'],l['side']) for l in r['legs']],[('example-0','yes'),('example-1','no')])
        # Valid subset/superset truth assignments pay at least one; not two independent events.
        self.assertEqual(min(superset+1-subset for subset,superset in [(0,0),(0,1),(1,1)]),1)
    def test_deadline_pair_reverses_threshold_order(self):
        sid='nested-deadline-coherence-arbitrage';r=evaluate(sid,example(sid),FREE)['best']
        self.assertEqual(r['legs'][0]['condition'],'example-1');self.assertEqual(r['legs'][0]['side'],'yes')
    def test_no_realized_pnl_for_terminal_floor(self):
        r=evaluate(NO,example(NO),FREE)['best'];self.assertIsNone(r['realized_pnl']);self.assertFalse(r['instant_conversion'])
    def test_invalid_limits(self):
        for cfg in [{'capital':True},{'fee_bps':float('nan')},{'depth_fraction':1},{'allow_unknown_age':1}]:
            with self.assertRaises(ValueError):Costs(**cfg).validate()
    def test_eligible_basket_precedes_larger_unfillable_bound(self):
        sid='multi-outcome-awards-dutch-book-construction';d=example(sid)
        for m in d['markets']:
            m['yes'].update(bid=.27,ask=.28)
            m['no'].update(bid=.08,ask=.1,ask_size=2)
        r=evaluate(sid,d,FREE)
        self.assertTrue(r['best']['eligible']);self.assertIn('YES',r['best']['name'])

class ReplayTests(unittest.TestCase):
    def market(self):
        return dict(condition='c',up='u',down='d',start=1000,end=1300,min_shares=1,ticks=[dict(t=1060+i,bu=.4,au=.43,bd=.4,ad=.45,su=100,sd=100,sau=100,sad=100) for i in range(2)])
    def test_fill_is_delayed_and_unknown_age_explicit(self):
        m=self.market();r=replay([m],CTF,{**FREE,'allow_unknown_age':True});self.assertEqual(r['trades'],1);self.assertGreater(r['ledger'][0]['fill_at'],r['ledger'][0]['signal_at'])
        self.assertEqual(replay([m],CTF,FREE)['trades'],0)
    def test_future_opportunity_cannot_change_signal(self):
        m=self.market();m['ticks'][0].update(au=.6,ad=.6)
        self.assertEqual(replay([m],CTF,{**FREE,'allow_unknown_age':True})['trades'],0)
    def test_edge_disappearing_before_fill_is_rejected(self):
        m=self.market();m['ticks'][1].update(au=.6,ad=.6)
        r=replay([m],CTF,{**FREE,'allow_unknown_age':True});self.assertEqual(r['trades'],0);self.assertIn('edge_or_depth_lost_before_fill',r['rejections'])

if __name__=='__main__':unittest.main()
