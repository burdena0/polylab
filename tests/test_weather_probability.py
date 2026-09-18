import unittest,copy
from datetime import datetime,timezone,timedelta
from polylab.weather_probability import parse_rule,parse_band,partition,daily_members,distribution,fit_bias,candidates

class WeatherProbabilityTests(unittest.TestCase):
    def setUp(self):
        self.rule=dict(station='KLGA',date='2026-09-18',timezone='America/New_York',timezone_verified=True,rounding='nearest_half_up',rounding_verified=True,metric='max',unit='C',sampling='hourly')
        self.bands=[dict(condition='cold',unit='C',label='19°C or below',lower=None,upper=19),dict(condition='mid',unit='C',label='20°C',lower=20,upper=20),dict(condition='hot',unit='C',label='21°C or higher',lower=21,upper=None)]
        self.member=dict(values_c=[19.,20.,21.,22.]*5,available_at=1000,day_start=2000,day_end=88400)
    def test_member_counts_partition_and_no_independence_claim(self):
        r=distribution(self.member,self.rule,self.bands,model='gfs',asof=1500)
        self.assertEqual([x['probability'] for x in r['probabilities']],[.25,.25,.5]);self.assertFalse(r['execution_eligible']);self.assertIn('No held-out station bias/spread calibration',r['blockers'])
    def test_fahrenheit_conversion_before_bucket_counting(self):
        rule={**self.rule,'unit':'F'};bands=[dict(condition='low',unit='F',label='67°F or below',lower=None,upper=67),dict(condition='high',unit='F',label='68°F or higher',lower=68,upper=None)]
        r=distribution(self.member,rule,bands,asof=1500)
        self.assertEqual(r['probabilities'][1]['probability'],.75)
    def test_observed_high_bounds_future_distribution(self):
        obs=dict(station='KLGA',date='2026-09-18',sampling='hourly',source_verified=True,observed_at=2500,available_at=2600,extreme_c=21)
        r=distribution(self.member,self.rule,self.bands,asof=3000,observed=obs)
        self.assertEqual(r['probabilities'][-1]['probability'],1.)
        for changes in [{'available_at':4000},{'station':'KJFK'},{'sampling':'all_readings'}]:
            with self.assertRaises(ValueError):distribution(self.member,self.rule,self.bands,asof=3000,observed={**obs,**changes})
    def test_gap_overlap_duplicate_and_missing_tails_rejected(self):
        for change in [('upper',18),('upper',20),('lower',0)]:
            b=copy.deepcopy(self.bands);b[0][change[0]]=change[1]
            with self.assertRaises(ValueError):partition(b)
        b=copy.deepcopy(self.bands);b[1]['condition']='cold'
        with self.assertRaises(ValueError):partition(b)
    def forecast(self,start,hours):
        times=[(start+timedelta(hours=i)).isoformat(timespec='minutes') for i in range(hours)]
        return dict(utc_offset_seconds=0,hourly={'time':times,**{f'temperature_2m_member{i:02}':[float(i)]*hours for i in range(20)}},hourly_units={f'temperature_2m_member{i:02}':'°C' for i in range(20)})
    def test_local_day_and_dst_are_not_fixed_24_hours(self):
        rule={**self.rule,'date':'2026-11-01'};f=self.forecast(datetime(2026,11,1),48)
        r=daily_members(f,rule,1000,1001);self.assertEqual(r['hours'],25);self.assertEqual(r['values_c'],list(range(20)))
        rule['date']='2026-03-08';f=self.forecast(datetime(2026,3,8),48)
        self.assertEqual(daily_members(f,rule,1000,1001)['hours'],23)
    def test_missing_hours_future_receipt_and_missing_members_rejected(self):
        f=self.forecast(datetime(2026,9,18),48)
        with self.assertRaises(ValueError):daily_members(f,self.rule,1002,1001)
        f['hourly']['time'][3]=f['hourly']['time'][4]
        with self.assertRaises(ValueError):daily_members(f,self.rule,1000,1001)
        f=self.forecast(datetime(2026,9,18),24)
        with self.assertRaises(ValueError):daily_members(f,self.rule,1000,1001)
    def test_bias_fit_uses_resolved_past_days_and_identity(self):
        rows=[dict(station='KLGA',metric='max',model='gfs',date=str(i),forecast_available_at=i*100,day_start=i*100+10,day_end=i*100+50,observed_available_at=i*100+60,resolution_verified=True,members_c=[19.,21.]*10,observed_c=22.) for i in range(20)]
        bias=fit_bias(rows,'KLGA','max','gfs',3000);self.assertEqual(bias['bias_c'],2);self.assertEqual(bias['samples'],20)
        with self.assertRaises(ValueError):fit_bias(rows,'KLGA','max','gfs',1000)
        rows[-1]['date']=rows[0]['date']
        with self.assertRaises(ValueError):fit_bias(rows,'KLGA','max','gfs',3000)
    def test_rules_extract_hourly_and_decline_wrong_source(self):
        market=dict(conditionId='one',description="highest temperature recorded by NOAA on 18 Sep '26. https://www.weather.gov/wrh/timeseries?site=klga Show Hourly Data whole degrees Fahrenheit after which any alterations will not be considered Weather Underground Daily Observations lowest bracket",resolutionSource='https://www.weather.gov/wrh/timeseries?site=klga',groupItemTitle='80-81°F')
        r=parse_rule(market);self.assertEqual(r['sampling'],'hourly');self.assertEqual(r['date'],'2026-09-18');self.assertFalse(r['timezone_verified']);self.assertEqual(parse_band(market)['upper'],81)
        market['description']=market['description'].replace('NOAA','Someone')
        with self.assertRaises(ValueError):parse_rule(market)
    def test_costed_candidates_are_expected_value_not_realized_profit(self):
        result=distribution(self.member,self.rule,self.bands,model='gfs',asof=1500)
        q=dict(condition='hot',exchange_at=1499,received_at=1499,fee_schedule=dict(condition='hot',received_at=1490,rate=.05,exponent=1,taker_only=True),minimum_shares=5,yes=dict(bid=.19,ask=.2,ask_size=100),no=dict(bid=.79,ask=.8,ask_size=100))
        rows=candidates(result,[q],1500);self.assertGreater(rows[0]['expected_net_pnl'],0);self.assertFalse(rows[0]['execution_eligible']);self.assertIn('No held-out station bias/spread calibration',rows[0]['blockers'])
        with self.assertRaises(ValueError):candidates(result,[{**q,'exchange_at':1400}],1500)

if __name__=='__main__':unittest.main()
