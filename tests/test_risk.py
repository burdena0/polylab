import copy,unittest
import numpy as np
from polylab.risk import *
from polylab.risk_replay import simulate
from polylab.research import features

class RiskTests(unittest.TestCase):
    def test_all_registered_controls(self):
        for sid in STRATEGIES:
            with self.subTest(sid=sid):self.assertFalse(evaluate(sid,example(sid)['document'])['execution_eligible'])
    def test_kelly_never_forces_minimum(self):
        d=example('kelly-optimal-sizing')['document'];d['probability']=.51
        self.assertEqual(kelly(d)['quantity'],0)
        d['probability']=.9;self.assertLessEqual(kelly(d)['budget'],7.5)
    def test_covariance_excludes_future_and_irregular_cadence(self):
        rows=[dict(t=1789683000+i,prices=[v,1-v]) for i,v in enumerate([.5,.51,.49,.5,.48])]
        result=realized_covariance(rows,1789683004);self.assertEqual(result['return_interval_seconds'],1)
        self.assertLess(result['covariance'][0][1],0)
        with self.assertRaises(ValueError):realized_covariance(rows,1789683003)
        rows[-1]['t']+=1
        with self.assertRaises(ValueError):realized_covariance(rows,1789683005)
    def test_volatility_budget_and_zero_vol(self):
        d=example('volatility-targeted-book-scaling')['document'];r=volatility(d)
        self.assertLessEqual(sum(r['allocations']),d['budget']);self.assertLessEqual(r['portfolio_volatility'],d['target_volatility']+1e-10)
        d['covariance']=[[0,0],[0,.01]];self.assertEqual(volatility(d)['allocations'][0],0)
    def test_covariance_must_be_psd(self):
        with self.assertRaises(ValueError):covariance([[1,2],[2,1]],2)
    def test_liquidity_uses_exit_depth_and_volume(self):
        d=example('liquidity-adjusted-position-limits')['document'];r=liquidity(d)
        self.assertEqual(r['maximum_shares'],15);d['recent_volume']=20;self.assertEqual(liquidity(d)['maximum_shares'],0)
        d['recent_volume']=None;d['bids']=[[.4,99999]];self.assertEqual(liquidity(d)['maximum_shares'],0)
    def test_factor_cap_applies_to_correlated_positions(self):
        d=example('resolution-correlation-budgeted-sizing')['document'];r=correlation(d)
        self.assertLessEqual(sum(r['allocations']),6+1e-6)
        d['factor_loadings']=[[1,-1]];r=correlation(d);self.assertLessEqual(r['gross_factor_exposure'][0],6+1e-6)
    def test_scenario_hedge_improves_worst_case(self):
        d=example('scenario-stress-allocation-engine')['document'];r=scenario(d)
        self.assertTrue(r['feasible']);self.assertGreater(r['worst_after'],r['current_worst']);self.assertLessEqual(r['spend'],1+1e-8);self.assertGreaterEqual(min(r['scenario_pnl']),-4)
    def test_infeasible_scenario_is_not_a_plan(self):
        d=example('scenario-stress-allocation-engine')['document'];d['budget']=0;r=scenario(d);self.assertFalse(r['feasible'])
    def test_minimum_size_cannot_break_stress_constraint(self):
        d=example('scenario-stress-allocation-engine')['document'];d['minimum_shares']=[100];r=scenario(d);self.assertFalse(r['feasible'])
    def test_netting_does_not_release_cash(self):
        r=netting(example('cross-market-net-exposure-netting')['document']);self.assertEqual(r['net_factor_shares']['same-outcome'],2);self.assertEqual(r['locked_cost'],9);self.assertEqual(r['collateral_released'],0)
    def test_governor_halts_and_requires_cooldown(self):
        g=DrawdownGovernor();g.update(100,0);self.assertEqual(g.update(90,1)['mode'],'reduced');self.assertTrue(g.update(80,2)['flatten']);self.assertEqual(g.update(81,100)['size_multiplier'],0)
        r=g.update(81,3602);self.assertTrue(r['restarted_after_cooldown']);self.assertEqual(g.high_watermark,100)
        with self.assertRaises(ValueError):g.update(81,100)
    def test_cost_gate_retains_budget_on_rejection(self):
        d=example('gas-settlement-cost-aware-rebalancing-cadence')['document'];d['total_cost']=3;r=cadence(d);self.assertFalse(r['allow']);self.assertEqual(r['monthly_remaining_after'],2)
    def test_bad_numeric_inputs(self):
        for x in [True,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):scalar(x,'x')

class RiskReplayTests(unittest.TestCase):
    def market(self):
        ticks=[]
        for i in range(300):
            mid=.20+min(i,60)*.01
            ticks.append(dict(t=1000+i,bu=mid-.005,au=mid+.005,bd=1-mid-.005,ad=1-mid+.005,su=100,sau=100,sd=100,sad=100))
        m=dict(condition='test',start=1000,end=1300,min_shares=1,ticks=ticks)
        return dict(market=m,features=features(m))
    def test_risk_replay_respects_latency_and_costs(self):
        r=simulate([self.market()],{},'baseline');self.assertEqual(r['trades'],1)
        for trade in r['ledger']:
            if trade['exit_time']:self.assertGreater(trade['exit_time'],trade['intent_time']);self.assertLess(trade['pnl'],0)
    def test_halt_has_delayed_flatten_intent(self):
        r=simulate([self.market()],{},'drawdown',soft=.0001,hard=.0002)
        self.assertTrue(any(x['reason']=='risk_flatten' for x in r['ledger']))
        t=r['ledger'][0];self.assertGreater(t['exit_time'],t['intent_time'])
    def test_liquidity_blocks_thin_exit(self):
        row=self.market()
        for t in row['market']['ticks']:t['su']=.1
        self.assertEqual(simulate([row],{},'liquidity')['trades'],0)
    def test_strict_age_rejects_cached_quotes(self):
        self.assertEqual(simulate([self.market()],{},'baseline',{'allow_unknown_age':False})['trades'],0)
    def test_missing_exit_keeps_basis_locked(self):
        row=self.market();row['market']['ticks']=row['market']['ticks'][:80]
        r=simulate([row],{},'baseline');self.assertGreater(r['open_basis'],0);self.assertEqual(r['realized_pnl'],0)

if __name__=='__main__':unittest.main()
