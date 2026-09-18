import unittest
from email.utils import formatdate
from polylab.us_http_age import response_age


class USHTTPAgeTests(unittest.TestCase):
    def receipt(self, age='10', date=1000, delay=1):
        headers = {'Date':formatdate(date,usegmt=True)}
        if age is not None: headers['Age']=age
        return dict(received_at=1000, round_trip_seconds=delay, public_cache_headers=headers)

    def test_transit_residence_and_date_each_contribute(self):
        self.assertEqual(response_age(self.receipt(),1003)['current_age_seconds'],14)
        self.assertEqual(response_age(self.receipt('1',980,2),1003)['current_age_seconds'],23)
        self.assertEqual(response_age(self.receipt('10, 11'),1003)['current_age_seconds'],14)

    def test_absent_age_does_not_become_verified_freshness(self):
        result = response_age(self.receipt(None,1000,.5),1000)
        self.assertFalse(result['explicit_age'])
        self.assertEqual(result['current_age_seconds'],.5)
        for bad in [self.receipt('-1'),self.receipt('NaN'),self.receipt('1',1010),self.receipt('1',1000,float('nan'))]:
            with self.assertRaises(ValueError): response_age(bad,1003)
        with self.assertRaises(ValueError): response_age(self.receipt(),999)
