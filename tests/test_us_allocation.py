import itertools, random, unittest
from copy import deepcopy
from decimal import Decimal
from polylab.us_allocation import select, simulate, signal_options

class AllocationTests(unittest.TestCase):
    def test_optimizer_matches_exhaustive_choices(self):
        rng = random.Random(38)
        for _ in range(30):
            cities = {str(c):[dict(cost_cents=rng.randint(1,500), expected=str(rng.randint(1,200)/100), slug=f'{c}-{i}') for i in range(3)] for c in range(4)}
            budget = rng.randint(10,1000)
            best = max(sum(Decimal(o['expected']) for o in subset if o) for subset in itertools.product(*[[None]+v for v in cities.values()]) if sum(o['cost_cents'] for o in subset if o)<=budget)
            chosen = select(cities, Decimal(budget)/100, 'expected_dollars')
            self.assertEqual(sum((Decimal(o['expected']) for o in chosen),Decimal(0)),best)
            self.assertLessEqual(sum(o['cost_cents'] for o in chosen),budget)

    def sample(self):
        cfg = dict(capital='50',reserve='40',entry_budget='5',max_quote_age_seconds=300,model_asof=0,beta=1.3738073703598581,min_expected_dollars='.10',entry_delay_seconds=60)
        group = dict(station='A',date='2026-09-01',target=1000,release=2000,rules=[dict(slug='x'),dict(slug='y')],payouts={'x':1,'y':0},histories={})
        for slug,mid in [('x',.8),('y',.2)]: group['histories'][slug]=[dict(t=t,mid=mid,ask=mid+.02,bid=mid-.02) for t in [999,1060]]
        return cfg,group

    def test_selection_ignores_future_quote_and_payout(self):
        cfg,g=self.sample(); changed=deepcopy(g)
        changed['payouts']={'x':0,'y':1}
        for points in changed['histories'].values(): points[1].update(ask=.99,bid=.01,mid=.5)
        a=simulate([g],cfg,'expected_dollars','0');b=simulate([changed],cfg,'expected_dollars','0')
        self.assertEqual(a['decisions'],b['decisions'])
        self.assertGreater(a['entries'],0)
        self.assertEqual(b['entries'],0)

    def test_unknown_settlement_remains_open(self):
        cfg,g=self.sample();g['payouts']={}
        r=simulate([g],cfg,'expected_dollars','0')
        self.assertGreater(r['entries'],0);self.assertEqual(r['exits'],0)
        self.assertEqual(Decimal(r['realized_pnl']),0)
        self.assertEqual(Decimal(r['cash'])+Decimal(r['open_basis']),50)
        self.assertGreaterEqual(Decimal(r['cash']),40)

    def test_stale_ladder_rejects_whole_city(self):
        cfg,g=self.sample();g['histories']['y'][0]['t']=600
        self.assertEqual(signal_options(g,cfg,'0')[0],[])

    def test_equal_budget_and_fractional_cent(self):
        opts={'a':[dict(cost_cents=501,expected='8')], 'b':[dict(cost_cents=500,expected='2')]}
        self.assertEqual(len(select(opts,Decimal('10.009'),'equal_budget')),1)
        self.assertEqual(sum(o['cost_cents'] for o in select(opts,Decimal('10.009'),'expected_dollars')),501)

if __name__ == '__main__': unittest.main()
