import unittest
from unittest.mock import patch
from polylab.us_group_adapter import load_station_groups


class USGroupAdapterTests(unittest.TestCase):
    def test_removes_only_redundant_station_without_mutating_registration(self):
        group = dict(station='KLAX',date='2026-09-08',rules=[dict(station='KLAX')])
        cfg = dict(station='KLAX',groups=[group])
        with patch('polylab.us_group_adapter.load_groups',return_value='loaded') as original:
            self.assertEqual(load_station_groups('root',cfg,[],{}),'loaded')
            self.assertEqual(original.call_args.args[1],dict(station='KLAX',groups=[dict(date=group['date'],rules=group['rules'])]))
            self.assertEqual(cfg['groups'][0]['station'],'KLAX')
        with self.assertRaises(ValueError):load_station_groups('root',{**cfg,'station':'KMDW'},[],{})
