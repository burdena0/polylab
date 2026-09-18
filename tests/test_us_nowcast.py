import unittest
from copy import deepcopy
from polylab.us_nowcast import observations,fit,prediction

class NowcastTests(unittest.TestCase):
    def test_precise_reports_and_delayed_availability(self):
        text='station,valid,tmpf,metar\nNYC,2026-09-18 10:00,99,KNYC 181000Z 20/15 RMK T02000150\nNYC,2026-09-18 11:00,99,KNYC 181100Z 20/15\n'
        rows,rejected=observations(text,'KNYC')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['temperature_f'],68)
        self.assertEqual(rows[0]['assumed_available_at']-rows[0]['observed_at'],1800);self.assertEqual(len(rejected),1)

    def test_conflicts_are_not_resolved_with_later_archive_order(self):
        text='station,valid,tmpf,metar\nNYC,2026-09-18 10:00,68,KNYC 181000Z RMK T02000150\nNYC,2026-09-18 10:00,70,KNYC 181000Z COR RMK T02100150\n'
        rows,rejected=observations(text,'KNYC');self.assertEqual(rows,[]);self.assertEqual(len(rejected),1)

    def training(self):
        return [dict(station='KNYC',date=str(i),features=[1.,i%4-2.,-i%3],blend_high_f=80,observed_high_f=81+.3*(i%4-2.),latest_assumed_available_at=100+i,target=200+i,label_available_at=300+i) for i in range(20)]

    def test_fit_rejects_future_labels_and_duplicate_days(self):
        rows=self.training();model=fit(rows,400);self.assertEqual(model['training_days'],20);self.assertGreaterEqual(model['std_f'],1)
        with self.assertRaises(ValueError):fit(rows,310)
        rows[-1]['date']=rows[0]['date']
        with self.assertRaises(ValueError):fit(rows,400)

    def test_prediction_never_uses_label_or_hard_observation_bound(self):
        model=fit(self.training(),400);r=dict(station='KNYC',date='2026-09-18',target=500,latest_assumed_available_at=499,features=[1.,0.,0.],blend_high_f=80,observed_high_f=999)
        rules=[dict(station='KNYC',date=r['date'],slug='a',lower=None,upper=80),dict(station='KNYC',date=r['date'],slug='b',lower=81,upper=None)]
        a=prediction(model,r,rules);r['observed_high_f']=-999;self.assertEqual(a,prediction(model,r,rules));self.assertAlmostEqual(sum(a['probabilities']),1)
        r['latest_assumed_available_at']=501
        with self.assertRaises(ValueError):prediction(model,r,rules)
