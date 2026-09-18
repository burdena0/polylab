import unittest,itertools,random
from decimal import Decimal as D
from copy import deepcopy
from polylab.us_multiband import pack_city,select,event_payoffs
from polylab.us_multiband_replay import simulate
from tests import test_us_allocation as fixtures

class MultiBandTests(unittest.TestCase):
    def test_two_stage_solver_matches_full_enumeration(self):
        rng=random.Random(117)
        for _ in range(20):
            groups={c:{s:[dict(slug=c+s,side=side,cost_cents=rng.randint(20,250),expected=str(rng.randint(1,100)/100)) for side in ['long','short']] for s in ['x','y']} for c in ['A','B']}
            opts={c:pack_city(contracts,300) for c,contracts in groups.items()}
            chosen=select(opts,D('4'),'multi_band')
            allchoices=list(itertools.product(*[[None]+options for contracts in groups.values() for options in contracts.values()]))
            valid=[rows for rows in allchoices if sum(o['cost_cents'] for o in rows if o)<=400 and all(sum(o['cost_cents'] for o in rows if o and o['slug'].startswith(c))<=300 for c in groups)]
            best=max(sum((D(o['expected']) for o in rows if o),D(0)) for rows in valid)
            self.assertEqual(sum((D(o['expected']) for o in chosen),D(0)),best)
            self.assertEqual(len({o['slug'] for o in chosen}),len(chosen))

    def test_same_event_payoffs_are_exclusive(self):
        rules=[dict(slug='cold',lower=None,upper=69),dict(slug='warm',lower=70,upper=None)]
        legs=[dict(slug=s,side='long',quantity=2,signal_price='.40') for s in ['cold','warm']]
        result=event_payoffs(legs,rules)
        self.assertEqual([D(r['pnl']) for r in result],[D('.34'),D('.34')])
        rules[1]['lower']=69
        with self.assertRaises(ValueError):event_payoffs(legs,rules)

    def test_future_changes_cannot_change_decision(self):
        cfg,g=fixtures.AllocationTests().sample();b=deepcopy(g);b['payouts']={'x':0,'y':1}
        for points in b['histories'].values():points[1].update(ask=.99,bid=.01,mid=.5)
        a=simulate([g],cfg,'multi_band','0');r=simulate([b],cfg,'multi_band','0')
        self.assertEqual(a['decisions'],r['decisions']);self.assertGreater(a['entries'],0);self.assertEqual(r['entries'],0)

    def test_single_band_control_is_identical(self):
        from polylab.us_allocation import simulate as original
        cfg,g=fixtures.AllocationTests().sample();a=simulate([g],cfg,'single_band','0');b=original([g],cfg,'expected_dollars','0')
        self.assertEqual(a['ledger'],b['ledger']);self.assertEqual(a['decisions'],b['decisions'])

    def test_unknown_settlement_keeps_basis_and_reserve(self):
        cfg,g=fixtures.AllocationTests().sample();g['payouts']={}
        r=simulate([g],cfg,'multi_band','0');self.assertEqual(r['exits'],0)
        self.assertEqual(D(r['cash'])+D(r['open_basis']),D('50'));self.assertGreaterEqual(D(r['cash']),40)
