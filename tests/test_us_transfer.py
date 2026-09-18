import unittest
from unittest.mock import patch
from copy import deepcopy
from polylab.us_transfer import run_arm

class USTransferTests(unittest.TestCase):
    def test_ablation_removes_only_forecast_weight_and_does_not_refit(self):
        model=dict(alpha=.006,beta=1.373,asof=100,calibration_dates=10);before=deepcopy(model)
        with patch('polylab.us_transfer.simulate',return_value={}) as replay:
            result=run_arm([], 'market_recalibrated',model,{},'0')
            self.assertEqual(replay.call_args.args[1],'benter')
            self.assertEqual(replay.call_args.args[2],{**model,'alpha':0.})
            self.assertEqual(result['strategy'],'market_recalibrated');self.assertEqual(model,before)
        with self.assertRaises(ValueError):run_arm([],'new_tuned_arm',model,{},'0')
