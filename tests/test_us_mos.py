import unittest
from datetime import datetime,timezone,timedelta
from polylab.us_mos import feature,fit,predict

class USMOSTests(unittest.TestCase):
    def test_previous_cycle_only_and_fixed_standard_day(self):
        runtime=datetime(2026,9,16,12,tzinfo=timezone.utc)
        rows=[dict(station='KNYC',model='GFS',runtime=runtime.isoformat(),ftime=(runtime+timedelta(hours=h)).isoformat(),tmp=70+h/10) for h in range(6,55,3)]
        r=feature(rows,'KNYC','GFS','2026-09-17');self.assertEqual(r['hours'],24);self.assertEqual(r['day_end']-r['day_start'],86400)
        self.assertEqual(r['runtime'],runtime.timestamp());self.assertFalse(r['availability_verified'])
        with self.assertRaises(ValueError):feature(rows[:3],'KNYC','GFS','2026-09-17')
        with self.assertRaises(ValueError):feature(rows,'KMDW','GFS','2026-09-17')
    def test_calibration_excludes_future_labels_and_requires_unique_days(self):
        rows=[dict(station='KNYC',date=str(i),forecast_assumed_available_at=i*100,day_start=i*100+10,day_end=i*100+20,observation_issued_at=i*100+30,observed_high_f=82,blend_high_f=80) for i in range(20)]
        m=fit(rows,'KNYC',2100);self.assertEqual(m['bias_f'],2);self.assertEqual(m['residual_std_f'],1)
        with self.assertRaises(ValueError):fit(rows,'KNYC',1900)
        with self.assertRaises(ValueError):fit(rows+rows[:1],'KNYC',2100)
    def test_probability_partition_and_availability(self):
        model=dict(station='KNYC',asof=1,bias_f=0,residual_std_f=2,training_days=30)
        f=dict(station='KNYC',date='2026-09-17',assumed_available_at=2,sampled_high_f=80)
        bands=[dict(condition='1',lower=None,upper=79,unit='F'),dict(condition='2',lower=80,upper=81,unit='F'),dict(condition='3',lower=82,upper=None,unit='F')]
        r=predict(model,f,f,bands,3);self.assertAlmostEqual(sum(p['probability'] for p in r['probabilities']),1)
        with self.assertRaises(ValueError):predict(model,f,f,bands,1)
