import unittest
from polylab.us_station_feed import observation,paired_snapshot,normalize

class StationFeedTests(unittest.TestCase):
    def test_same_raw_report_matches_across_prefixes(self):
        a=observation('KNYC',100,'METAR KNYC 180100Z 25/20',25,200,'awc')
        n=observation('KNYC',100,'KNYC 180100Z 25/20',{'value':25},220,'nws')
        self.assertEqual(a['report_key'],n['report_key'])
        row=paired_snapshot([a,n],['KNYC'])[0];self.assertTrue(row['same_report']);self.assertEqual(row['awc_newer_observation_seconds'],0);self.assertIsNone(row['profit'])

    def test_correction_and_wrong_station_not_merged(self):
        a=observation('KNYC',100,'KNYC 180100Z 25/20',25,200,'awc')
        b=observation('KNYC',100,'KNYC 180100Z COR 24/20',24,200,'nws')
        self.assertNotEqual(a['report_key'],b['report_key'])
        with self.assertRaises(ValueError):observation('KLAX',100,'KNYC 180100Z 25/20',25,200,'awc')

    def test_local_receipt_cannot_be_replaced_by_provider_time(self):
        raw=[dict(icaoId='KNYC',obsTime=100,rawOb='KNYC 180100Z 25/20',temp=25,receiptTime='1970-01-01T00:01:41Z')]
        result=normalize(raw,{'received_at':200},['KNYC'],'awc')[0]
        self.assertEqual(result['available_at'],200)
        with self.assertRaises(ValueError):normalize(raw,{'received_at':99},['KNYC'],'awc')

if __name__=='__main__':unittest.main()
