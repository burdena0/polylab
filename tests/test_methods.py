import unittest,math,json,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from polylab.probability import *
from polylab.research import Config,features,simulate,packet
from polylab.weather import WeatherArchive,levels
from polylab.guide import guide_probability,parse_timestamp

def market():
    rows=[dict(t=1000+i,bu=.29,au=.31,bd=.68,ad=.70,su=100,sau=100,sd=100,sad=100) for i in range(300)]
    return dict(start=1000,end=1300,condition='test',label=1,min_shares=5,ticks=rows)
def model():return dict(fundamental={'weights':[2,0,0,0,0,0,0],'mean':[0]*6,'scale':[1]*6},benter={'alpha':1,'beta':0},base_rate=.9,public_calibration={'weights':[0,1],'mean':[0],'scale':[1]},calibration_n=100)

class ProbabilityTests(unittest.TestCase):
    def test_coinbase_nanosecond_timestamp(self):
        self.assertAlmostEqual(parse_timestamp('2026-09-17T22:01:04.112998221Z'),parse_timestamp('2026-09-17T22:01:04.112998Z'),places=5)
    def test_paper_example(self):
        p=odds_to_probabilities([1.8,3.75,4.33])['probabilities']
        np.testing.assert_allclose(p,[.535,.250,.215],atol=.001)
    def test_normalization(self):self.assertAlmostEqual(sum(odds_to_probabilities([2,3,4],'normalization')['probabilities']),1)
    def test_fair_odds(self):self.assertEqual(odds_to_probabilities([2,2])['z'],0)
    def test_shin_binary(self):
        p=odds_to_probabilities([1/.6,1/.45])['probabilities'];self.assertAlmostEqual(p[0],.575,places=8)
    def test_shin_underround_rejected(self):
        with self.assertRaises(ValueError):odds_to_probabilities([3,3])
    def test_invalid_odds(self):
        for odds in [[1,3],[math.nan,2],[2],[0,3]]:
            with self.assertRaises(ValueError):odds_to_probabilities(odds)
    def test_benter_limits(self):
        np.testing.assert_allclose(benter_combine([.7,.3],[.4,.6],1,0),[.7,.3]);np.testing.assert_allclose(benter_combine([.7,.3],[.4,.6],0,1),[.4,.6])
    def test_benter_multinomial(self):self.assertAlmostEqual(sum(benter_combine([.2,.3,.5],[.3,.3,.4],.4,.7)),1)
    def test_kelly_correct_payoff(self):self.assertAlmostEqual(fractional_kelly(50,.7,.5,.1),2)
    def test_kelly_no_forced_minimum(self):self.assertEqual(fractional_kelly(50,.4,.5),0)
    def test_ofi_definition(self):
        a={'bu':.4,'au':.5,'su':10,'sau':20};b={'bu':.41,'au':.5,'su':15,'sau':18};self.assertEqual(event_ofi(a,b),17)
    def test_inventory_skews_quotes(self):
        a=avellaneda_stoikov(.5,0,.0001,60);b=avellaneda_stoikov(.5,10,.0001,60);self.assertLess(b['bid'],a['bid']);self.assertLess(b['ask'],a['ask'])
    def test_forecast_scores(self):self.assertAlmostEqual(scores([.5,.5],[0,1])['brier'],.25)
    def test_guide_threshold_and_direction(self):
        self.assertIsNone(guide_probability(.5,.05));self.assertGreater(guide_probability(.5,1),.5);self.assertLess(guide_probability(.5,-1),.5)

class ReplayTests(unittest.TestCase):
    def test_features_do_not_see_future(self):
        m=market();f=features(m)
        m['label']=0
        for t in m['ticks'][61:]:t['bu']=.01;t['au']=.02
        self.assertEqual(f,features(m))
    def test_packet_has_no_target(self):
        m=market();p=packet({'market':m,'features':features(m)},model());s=json.dumps(p)
        self.assertNotIn('label',s);self.assertNotIn('condition',s);self.assertNotIn('1000',s)
    def test_delayed_fill_and_risk(self):
        m=market();r=simulate([dict(market=m,features=features(m))],'base-rate-exploitation',model())
        self.assertEqual(r['trades'],1);self.assertGreater(r['ledger'][0]['entry_time'],1060);self.assertLessEqual(r['ledger'][0]['cost'],7.5);self.assertGreater(r['ledger'][0]['exit_time'],r['ledger'][0]['entry_time'])
    def test_freshness_unknown_rejects(self):
        m=market();r=simulate([dict(market=m,features=features(m))],'base-rate-exploitation',model(),Config(allow_unknown_age=False));self.assertEqual(r['trades'],0)
    def test_minimum_shares_not_waived(self):
        m=market();m['min_shares']=10000;r=simulate([dict(market=m,features=features(m))],'base-rate-exploitation',model());self.assertEqual(r['trades'],0)
    def test_veto_prevents_entry(self):
        m=market();r=simulate([dict(market=m,features=features(m))],'base-rate-exploitation',model(),decisions={'0':False});self.assertEqual(r['trades'],0)
    def test_missing_exit_does_not_release_capital(self):
        m=market();m['ticks']=m['ticks'][:100];r=simulate([dict(market=m,features=features(m))],'base-rate-exploitation',model());self.assertGreater(r['open_basis'],0);self.assertEqual(r['realized_pnl'],0);self.assertLess(r['equity'],50)
    def test_invalid_config(self):
        for kw in [{'capital':True},{'kelly':1},{'slippage':float('nan')},{'max_trade':-1}]:
            with self.assertRaises(ValueError):Config(**kw).validate()

class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.patcher=patch('polylab.weather.ROOT',Path(self.temp.name));self.patcher.start();self.w=WeatherArchive();self.w.mapping={'t':{'condition':'c','city':'London','date':'2026-09-17','region':'Europe','outcome':'Yes','question':'Temperature','token':'t'}}
    def tearDown(self):self.patcher.stop();self.temp.cleanup()
    def test_delta_requires_snapshot(self):
        self.w.on_message(None,json.dumps({'event_type':'price_change','market':'c','timestamp':'100000','price_changes':[{'asset_id':'t','side':'BUY','price':'.4','size':'10'}]}));self.assertFalse(self.w.books)
    def test_full_book_delta_and_disconnect(self):
        self.w.on_message(None,json.dumps({'event_type':'book','market':'c','asset_id':'t','timestamp':'100000','bids':[{'price':'.4','size':'10'}],'asks':[{'price':'.5','size':'20'}]}))
        self.w.on_message(None,json.dumps({'event_type':'price_change','market':'c','timestamp':'101000','price_changes':[{'asset_id':'t','side':'BUY','price':'.4','size':'0'}]}));self.assertFalse(self.w.books['t']['bids']);self.w.on_close();self.assertFalse(self.w.books);self.assertEqual(self.w.state['gaps'],1)
    def test_market_mismatch(self):
        self.w.on_message(None,json.dumps({'event_type':'book','market':'wrong','asset_id':'t'}));self.assertFalse(self.w.books)
    def test_archive_path_traversal(self):
        with self.assertRaises(ValueError):self.w.replay('../.env')
    def test_invalid_level(self):
        with self.assertRaises(ValueError):levels([{'price':'.2','size':'NaN'}])

if __name__=='__main__':unittest.main()
