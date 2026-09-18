import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from polylab.fees import observed_schedule,validate,fee_usdc
from polylab.paper import PaperTrader

class FeeTests(unittest.TestCase):
    def setUp(self):
        self.raw=dict(conditionId='test',feesEnabled=True,feeSchedule=dict(rate=.07,exponent=1,takerOnly=True))
        self.schedule=observed_schedule(self.raw,1000)
    def test_matches_official_crypto_table_and_symmetry(self):
        for p,expected in [(.1,.63),(.5,1.75),(.9,.63)]:self.assertAlmostEqual(fee_usdc(100,p,self.schedule),expected)
        self.assertEqual(fee_usdc(100,.5,self.schedule,maker=True),0)
    def test_no_legacy_base_fee_fallback_or_unknown_curve(self):
        for raw in [dict(conditionId='test',feesEnabled=True,takerBaseFee=1000),{**self.raw,'feeSchedule':dict(rate=.07,exponent=2,takerOnly=True)},{**self.raw,'feesEnabled':None}]:
            with self.assertRaises(ValueError):observed_schedule(raw,1000)
    def test_receipt_identity_and_time(self):
        for condition,asof in [('wrong',1001),('test',999),('test',2000)]:
            with self.assertRaises(ValueError):validate(self.schedule,condition,asof)
    def test_explicit_fee_free_and_small_fee_rounding(self):
        free=observed_schedule(dict(conditionId='free',feesEnabled=False),1000)
        self.assertEqual(fee_usdc(100,.5,free),0)
        self.assertEqual(fee_usdc(.00001,.01,self.schedule),0)
    def test_paper_cash_and_ledger_include_curve_fees(self):
        with tempfile.TemporaryDirectory() as d,patch('polylab.paper.ROOT',Path(d)):
            p=PaperTrader();p.state['pending']=dict(condition='test',side='u',p=.9,intent=1060);p.state['decided']=['test']
            m=dict(condition='test',start=1000,end=1300,min_shares=5,fee_schedule=self.schedule)
            t=dict(t=1061,bu=.49,au=.5,bd=.49,ad=.5,su=100,sau=100,sd=100,sad=100)
            p.step(m,t,{});position=p.state['positions'][0];q=position['quantity'];fee=fee_usdc(q,.501,self.schedule)
            self.assertAlmostEqual(50-p.state['cash'],q*.501+fee)
            p.step(m,{**t,'t':1240},{});p.step(m,{**t,'t':1241},{})
            expected=q*.489-fee_usdc(q,.489,self.schedule)-(q*.501+fee)
            self.assertAlmostEqual(p.state['realized_pnl'],expected)
            rows=[json.loads(x) for x in (p.path.parent/'trades.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),2);self.assertTrue(all('fee_schedule' in r for r in rows));self.assertFalse(p.state['positions'])

if __name__=='__main__':unittest.main()
