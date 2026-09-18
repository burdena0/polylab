import unittest
from polylab.us_portfolio import allocate


class USPortfolioTests(unittest.TestCase):
    def test_shared_cash_uses_profit_priority_and_never_future_proceeds(self):
        cfg = dict(capital='50', reserve='40', entry_budget='5', monthly_subscription=200, min_expected_dollars='.1')
        def candidate(slug, probability, entry=100, release=1000):
            return dict(slug=slug, probability=probability, price='.9', side='long', signal_t=entry-60,
                        entry_t=entry, release=release, payout=1, station='KNYC', date='2026-09-08')
        result = allocate([candidate('A-low', .93), candidate('Z-high', .99), candidate('M-mid', .97),
                           candidate('before-proceeds', .99, 500, 1500), candidate('after-proceeds', .99, 1000, 2000)], cfg, 0, 2000)
        buys = [t for t in result['ledger'] if t['kind']=='buy']
        self.assertEqual([t['slug'] for t in buys], ['Z-high', 'M-mid', 'after-proceeds'])
        self.assertEqual(result['entries'], 3)
        self.assertEqual(result['exits'], 3)
        self.assertEqual(result['realized_pnl'], '1.41')
        self.assertTrue(all(float(t['cash']) >= 40 for t in result['ledger']))
        self.assertEqual(len(result['rejections']), 2)
        self.assertEqual(result['open_basis'], '0')

    def test_missing_payout_keeps_basis_and_duplicate_contract_rejected(self):
        cfg = dict(capital='50', reserve='40', entry_budget='5', monthly_subscription=200, min_expected_dollars='.1')
        candidate = dict(slug='A', probability=.99, price='.9', side='long', signal_t=1, entry_t=100,
                         release=200, payout=None, station='KLAX', date='2026-09-08')
        result = allocate([candidate], cfg, 0, 200)
        self.assertEqual(result['positions'], 1)
        self.assertEqual(result['realized_pnl'], '0')
        self.assertEqual(result['open_basis'], '4.53')
        with self.assertRaises(ValueError):
            allocate([candidate, candidate], cfg, 0, 200)
