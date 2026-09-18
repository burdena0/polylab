import unittest
from tools.summarize_us_edge import metrics


class EdgeDiagnosticTests(unittest.TestCase):
    def test_model_expectation_is_separate_from_realized_and_expense(self):
        row = dict(strategy='example', slippage_per_side='0', entries=1, exits=1,
                   realized_pnl='4.80', fees='.20', open_basis='0',
                   period_start=0, period_end=86400, subscription_expense_prorated=6.,
                   realized_after_subscription=-1.2,
                   ledger=[dict(kind='buy', slug='A', probability=.6, quantity='10', price='.5', fee='.20', t=3600),
                           dict(kind='settlement', slug='A', pnl='4.80', t=7200)])
        result = metrics(row, '50')
        self.assertEqual(result['estimated_entry_edge_sum'], '0.80')
        self.assertEqual(result['realized_pnl'], '4.80')
        self.assertEqual(result['pnl_without_largest_winner'], '0.00')
        self.assertEqual(result['average_closed_holding_hours'], 1.)
        self.assertAlmostEqual(result['estimated_entry_edge_less_subscription'], -5.2)
