import unittest
from copy import deepcopy
from polylab.us_benter import combine,fit_combination,simulate,exclusive_outcome

def config():
    return dict(station='KNYC',forecast_training=['2026-07-01','2026-07-20'],combination_training=['2026-08-01','2026-08-31'],minimum_combination_dates=10,probability_floor=1e-6,ridge_anchor=[0,1],ridge_penalty=.01,weight_bounds=[0,4],capital='50',reserve='40',entry_budget='5',entry_delay_seconds=60,max_quote_age_seconds=300,min_expected_dollars='.10',monthly_subscription=200)

class USBenterTests(unittest.TestCase):
    def test_fit_rejects_test_rows_duplicate_dates_and_future_labels(self):
        rows=[dict(date=f'2026-08-{i+1:02}',role='calibration',station='KNYC',target=100+i,label_available_at=200+i,outcome=i%2,fundamental=[.4,.6],market=[.6,.4]) for i in range(12)]
        model=fit_combination(rows,config(),300)
        self.assertEqual(model['calibration_dates'],12)
        for key,value in [('role','test'),('date',rows[1]['date']),('label_available_at',301),('station','KLAX')]:
            bad=deepcopy(rows);bad[0][key]=value
            with self.assertRaises(ValueError):fit_combination(bad,config(),300)
        with self.assertRaises(ValueError):fit_combination(rows[:9],config(),300)

    def test_combination_anchors_extreme_tails_and_exclusive_labels(self):
        p=combine([0,1],[.8,.2],[0,1]);self.assertAlmostEqual(p[0],.8)
        p=combine([0,1],[.8,.2],[.5,.5]);self.assertAlmostEqual(sum(p),1);self.assertGreater(p[0],0)
        rules=[dict(slug='a'),dict(slug='b')]
        self.assertIsNone(exclusive_outcome({'a':.5,'b':.5},rules))
        self.assertEqual(exclusive_outcome({'a':0.,'b':1.},rules),1)

    def test_portfolio_locks_cash_across_overlapping_dates_and_rejects_training(self):
        groups=[]
        for i in range(4):
            a,b=f'a{i}',f'b{i}';t=1000+i*100
            groups.append(dict(date=f'2026-09-{8+i:02}',role='test',target=t,rules=[dict(slug=a,market_id=a),dict(slug=b,market_id=b)],histories={a:[dict(t=t,bid=.19,ask=.20,mid=.195),dict(t=t+60,bid=.19,ask=.20,mid=.195)],b:[dict(t=t,bid=.79,ask=.80,mid=.795),dict(t=t+60,bid=.79,ask=.80,mid=.795)]},fundamental=[.8,.2],market=[.2,.8],asks=[.2,.8],release=2000+i,outcome=0,payouts={a:1.,b:0.}))
        report=simulate(groups,'mos_only',None,config(),'0')
        self.assertEqual(report['entries'],3);self.assertEqual(report['exits'],3)
        buys=[r for r in report['ledger'] if r['kind']=='buy']
        self.assertEqual(float(buys[-1]['quantity']),1)  # Remaining cash funds one whole contract.
        self.assertLessEqual(sum(float(r['price'])*float(r['quantity'])+float(r['fee']) for r in buys),10)
        self.assertEqual(report['positions'],0);self.assertGreater(float(report['realized_pnl']),0)
        self.assertTrue(all(p['cash']>=40 for p in report['curve']))
        self.assertAlmostEqual(float(report['cash'])-50,float(report['realized_pnl']))
        groups[0]['role']='calibration'
        with self.assertRaises(ValueError):simulate(groups,'mos_only',None,config(),'0')
