import unittest
from datetime import datetime,timezone,timedelta
from polylab.us_weather import parse_contract,window,parse_cli,probabilities,scan_contract

def market(term='between 80F and 81F',date='2026-09-17'):
    return dict(id='123',slug='tc-temp-nychigh-gte80lt81f',description=f"Will the highest temperature recorded at Central Park (KNYC) in New York City for {date} as reported by the National Weather Service's Climatological Report (Daily) be {term}? Outcome verified from NWS Climatological Report.")

class USWeatherTests(unittest.TestCase):
    def test_prose_bounds_take_priority_over_slug(self):
        rule=parse_contract(market());self.assertEqual((rule['lower'],rule['upper']),(80,81));self.assertEqual(rule['station'],'KNYC')
        self.assertIsNone(parse_contract(market('less than or equal to 79F'))['lower'])
        with self.assertRaises(ValueError):parse_contract({**market(),'description':market()['description'].replace('KNYC','KLGA')})
    def test_standard_time_stays_24_hours_through_dst(self):
        for day in ['2026-03-08','2026-11-01','2026-09-17']:
            start,end=window(parse_contract(market(date=day)))
            self.assertEqual(end-start,86400);self.assertEqual(datetime.fromtimestamp(start,timezone.utc).hour,5)
    def test_cli_interim_is_not_final_and_observed_column_only(self):
        text='CLINYC\nCLIMATE SUMMARY FOR SEPTEMBER 17 2026\nVALID TODAY AS OF 0400 PM LOCAL TIME.\nTEMPERATURE (F)\n TODAY\n MAXIMUM 82 1255 PM 93 1991\n MINIMUM 70 611 AM 45 1986\nPRECIPITATION\nMAXIMUM TEMPERATURE (F) 76 91 1891'
        d=dict(id='abc',productCode='CLI',issuanceTime='2026-09-17T20:50:00Z',productText=text)
        r=parse_cli(d,'KNYC',1800000000);self.assertEqual(r['max_f'],82);self.assertTrue(r['interim']);self.assertFalse(r['exchange_settlement_verified'])
        with self.assertRaises(ValueError):parse_cli(d,'KMDW',1800000000)
        with self.assertRaises(ValueError):parse_cli(d,'KNYC',0)
        d['productText']=text.replace('MAXIMUM 82','MAXIMUM MM')
        with self.assertRaises(ValueError):parse_cli(d,'KNYC',1800000000)
    def test_prior_day_cli_requires_complete_window(self):
        text='CLINYC\nCLIMATE SUMMARY FOR SEPTEMBER 16 2026\nTEMPERATURE (F)\n YESTERDAY\n MAXIMUM 77 1230 PM\n MINIMUM 58 300 AM\nPRECIPITATION'
        d=dict(id='abc',productCode='CLI',issuanceTime='2026-09-17T06:32:00Z',productText=text)
        self.assertTrue(parse_cli(d,'KNYC',1800000000)['complete_day'])
    def test_member_window_and_integer_cli_conditioning(self):
        rule=parse_contract(market(date='2026-09-18'));start,end=window(rule)
        times=[datetime.fromtimestamp(start+i*3600,timezone.utc).strftime('%Y-%m-%dT%H:%M') for i in range(24)]
        keys=['temperature_2m_member'+str(i) for i in range(20)]
        forecast=dict(utc_offset_seconds=0,hourly={'time':times,**{k:[25]*24 for k in keys}},hourly_units={k:'C' for k in keys})
        bands=[dict(condition='123',label='low',lower=None,upper=79,unit='F'),dict(condition='124',label='middle',lower=80,upper=81,unit='F'),dict(condition='125',label='high',lower=82,upper=None,unit='F')]
        r=probabilities(forecast,{'available_at':start-1},rule,bands,'test',start-1)
        self.assertEqual(r['hours'],24);self.assertEqual([p['probability'] for p in r['probabilities']],[1,0,0])
        cli=dict(station='KNYC',date='2026-09-18',max_f=82,issued_at=start+5,available_at=start+10)
        r=probabilities(forecast,{'available_at':start-1},rule,bands,'test',start+20,cli)
        self.assertEqual([p['probability'] for p in r['probabilities']],[0,0,1]);self.assertFalse(r['execution_eligible'])
        with self.assertRaises(ValueError):probabilities(forecast,{'available_at':start+50},rule,bands,'test',start+20)
        forecast['hourly']['time']=times[:-1]
        with self.assertRaises(ValueError):probabilities(forecast,{'available_at':start-1},rule,bands,'test',start-1)
    def test_us_quote_scan_uses_worst_model_and_fee_bounded_whole_lots(self):
        rule=parse_contract(market())
        models=[dict(station='KNYC',date='2026-09-17',metric='max',forecast_available_at=90,probabilities=[dict(condition='123',probability=p)]) for p in [.7,.6,.8]]
        book=dict(slug=rule['slug'],valid=True,state='MARKET_STATE_OPEN',exchange_at=99,received_at=100,bids=[[.4,50]],offers=[[.42,30]])
        r=scan_contract(rule,models,book,100)
        self.assertEqual(r[0]['probability_min_across_models'],.6);self.assertEqual(r[0]['quantity'],7)
        self.assertLess(float(r[0]['cost']),5);self.assertFalse(r[0]['execution_eligible'])
        with self.assertRaises(ValueError):scan_contract(rule,models,book,106)
