import unittest
from polylab.us_weather_replay import choose_entry

class USWeatherReplayTests(unittest.TestCase):
    def test_choice_uses_signal_not_future_price_and_preserves_delay(self):
        rules=[dict(slug='a',market_id='1'),dict(slug='b',market_id='2')]
        histories={'a':[dict(t=100,bid=.2,ask=.22,mid=.21),dict(t=160,bid=.4,ask=.42,mid=.41)],'b':[dict(t=100,bid=.7,ask=.72,mid=.71),dict(t=160,bid=.1,ask=.12,mid=.11)]}
        result,reason=choose_entry(rules,{'1':.6,'2':.4},histories,100,60,300,'5','.1','0')
        self.assertEqual(result['slug'],'a');self.assertEqual(result['side'],'long');self.assertEqual(result['entry_t'],160);self.assertEqual(result['price'],'0.42')
        histories['a'][-1].update(bid=.8,ask=.82)
        self.assertEqual(choose_entry(rules,{'1':.6,'2':.4},histories,100,60,300,'5','.1','0')[1],'Edge disappeared before delayed entry')
    def test_incomplete_ladder_and_expired_quote_are_rejected(self):
        rules=[dict(slug='a',market_id='1'),dict(slug='b',market_id='2')]
        h={'a':[dict(t=1,bid=.2,ask=.22,mid=.21)]}
        self.assertIsNone(choose_entry(rules,{'1':.6,'2':.4},h,400,60,300,'5','.1','0')[0])
