import unittest
from polylab.public_inputs import stations_from_rules
from polylab.oracle import normalize

class PublicInputTests(unittest.TestCase):
    def test_station_mapping_is_exact_host_and_rule_parameter(self):
        self.assertEqual(stations_from_rules('Use https://www.weather.gov/wrh/timeseries?site=klga and https://weather.gov/wrh/timeseries?site=EGLC.'),{'KLGA','EGLC'})
        self.assertEqual(stations_from_rules('Use https://weather.gov/wrh/timeseries?site=EGLC'),{'EGLC'})
        self.assertEqual(stations_from_rules('KLGA https://weather.gov.evil.test/?site=KDAL https://example.com/?site=KLGA'),set())
    def test_twap_keeps_exact_price_and_all_three_clocks(self):
        raw=dict(topic='crypto_prices_twap_thirty',type='update',timestamp=1000200,payload=dict(symbol='btc/usd',window_s=30,timestamp=1000000,full_accuracy_value='65000500000000000000000'))
        row=normalize(raw,1001)
        self.assertEqual(row['value'],'65000.5');self.assertEqual(row['age_seconds'],1);self.assertEqual(row['published_at'],1000.2)
        with self.assertRaises(ValueError):normalize(raw,990)
        raw['payload']['window_s']=60
        with self.assertRaises(ValueError):normalize(raw,1001)
    def test_unrelated_oracle_message_cannot_be_used(self):
        self.assertIsNone(normalize({'topic':'crypto_prices'},1001))

if __name__=='__main__':unittest.main()
