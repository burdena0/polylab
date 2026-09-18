import unittest
from decimal import Decimal as D
from polylab.us_accounting import taker_fees,maker_fee,conservative_taker_fee,Account

class USAccountingTests(unittest.TestCase):
    def test_documented_examples_and_half_even(self):
        self.assertEqual(conservative_taker_fee('.10',1000),D('6.26'))
        self.assertEqual(conservative_taker_fee('.65',1000),D('15.81'))
        self.assertEqual(maker_fee('.10',1000),D('-1.12'))
        self.assertEqual(conservative_taker_fee('.5',100),D('1.74'))
    def test_cumulative_cap_can_reduce_but_not_increase_fill_fee(self):
        fees=taker_fees([('.5',1)]*4)
        self.assertEqual(fees,[D('.02'),D('.01'),D('.02'),D('.02')])
        self.assertEqual(sum(fees),D('.07'))
        # Small fills round down independently; no later overcharge to catch up.
        self.assertEqual(taker_fees([('.1',1)]*4),[D('.01'),D('.00'),D('.01'),D('.01')])
    def test_reserve_cash_profit_and_nonbinary_settlement(self):
        a=Account();a.buy('x','.5',10,1)
        self.assertEqual(a.cash,D('44.83'))
        with self.assertRaises(ValueError):a.buy('y','.5',10,2)
        a.close('x','.65',3,settlement=True)
        self.assertEqual(a.snapshot()['realized_pnl'],'1.33')
        self.assertEqual(a.cash,D('51.33'))
    def test_whole_simulation_and_atomic_rejection(self):
        a=Account()
        with self.assertRaises(ValueError):a.buy('x','.5',1.5,1)
        self.assertEqual(a.cash,D(50))
        a.buy('x','.5',1,2)
        with self.assertRaises(ValueError):a.close('x','.6',1)
        self.assertEqual(a.snapshot()['positions'],1)
