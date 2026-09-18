import unittest
from polylab.us_station_feed_v2 import normalize,observation,paired_snapshot
class FeedV2Tests(unittest.TestCase):
    def test_missing_raw_retained_but_never_matched(self):
        row={'properties':{'station':'https://api.weather.gov/stations/KLAX','timestamp':'1970-01-01T00:01:40Z','rawMessage':'','temperature':{'value':24}}}
        n=normalize(row,{'received_at':200},['KLAX'],'nws','KLAX')[0]
        self.assertIsNone(n['report_key']);self.assertFalse(n['raw_message_available'])
        a=observation('KLAX',100,'',24,201,'awc')
        self.assertFalse(paired_snapshot([a,n],['KLAX'])[0]['same_report'])
        self.assertEqual(paired_snapshot([a,n],['KLAX'])[0]['awc_newer_observation_seconds'],0)
    def test_raw_identity_and_source_only_corrections(self):
        a=observation('KLAX',100,'METAR KLAX 010100Z 24/20',24,200,'awc')
        n=observation('KLAX',100,'KLAX 010100Z 24/20',24,201,'nws')
        self.assertTrue(paired_snapshot([a,n],['KLAX'])[0]['same_report'])
        x=observation('KLAX',100,'',24,201,'nws');y=observation('KLAX',100,'',25,201,'nws')
        self.assertNotEqual(x['observation_key'],y['observation_key'])
    def test_station_uri_still_required(self):
        row={'properties':{'station':'https://api.weather.gov/stations/KNYC'}}
        with self.assertRaises(ValueError):normalize(row,{'received_at':200},['KLAX'],'nws','KLAX')
