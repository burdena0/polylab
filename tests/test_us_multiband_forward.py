import unittest
from copy import deepcopy
from decimal import Decimal as D
from email.utils import formatdate
from polylab.us_multiband_forward import plan,evaluate,usable

class ForwardMultiBandTests(unittest.TestCase):
    def sample(self):
        cfg=dict(capital='50',reserve='40',entry_budget='5',target=1000,entry_delay_seconds=60,entry_deadline=1300,settlement_not_before=2000,
                 max_http_age_seconds=45,max_signal_http_age_seconds=300,max_quote_age_seconds=300,beta=1.3738073703598581,model_asof=0,min_expected_dollars='.10',slippage_per_side='.005',depth_fraction='.25')
        o=dict(station='KNYC',date='2026-09-18',slug='warm',side='long',probability=.99,quantity=9,cost_cents=500)
        planned=dict(arms=[dict(method='multi_band',selected=[o])])
        raw=dict(book=dict(slug='warm',bids=[[.49,100]],offers=[[.50,8]],exchange_at=500,state='MARKET_STATE_OPEN',valid=True),
                 receipt=dict(requested_at=1060,received_at=1062,round_trip_seconds=2,public_cache_headers={'Date':formatdate(1062,usegmt=True),'Age':'0'}))
        return cfg,planned,raw

    def test_observed_depth_caps_size_without_claiming_execution(self):
        cfg,p,r=self.sample();out=evaluate(p,{'warm':r},{},cfg)['results'][0]
        self.assertEqual(out['ledger'][0]['quantity'],'2');self.assertEqual(out['positions'],1)
        self.assertEqual(D(out['cash'])+D(out['open_basis']),50);self.assertFalse(out['fill_validated'])
        self.assertEqual(out['realized_pnl'],'0')

    def test_later_payout_does_not_change_entry(self):
        cfg,p,r=self.sample();a=evaluate(p,{'warm':r},{},cfg)['results'][0]
        payouts={'warm':dict(response=dict(slug='warm',settlement='1'),receipt=dict(requested_at=2000,received_at=2001))}
        b=evaluate(p,{'warm':r},payouts,cfg)['results'][0]
        self.assertEqual(a['ledger'][0],b['ledger'][0]);self.assertEqual(b['positions'],0)
        self.assertEqual(D(b['realized_pnl']),D('2')-D(a['open_basis']))
        payouts['warm']['receipt']['requested_at']=1999
        with self.assertRaises(ValueError):evaluate(p,{'warm':r},payouts,cfg)

    def test_stale_http_delayed_window_and_identity(self):
        cfg,p,r=self.sample();r['receipt']['public_cache_headers']['Age']='60'
        self.assertEqual(evaluate(p,{'warm':r},{},cfg)['results'][0]['positions'],0)
        cfg,p,r=self.sample();r['receipt']['requested_at']=1059
        self.assertEqual(evaluate(p,{'warm':r},{},cfg)['results'][0]['positions'],0)
        cfg,p,r=self.sample();r['book']['slug']='wrong'
        with self.assertRaises(ValueError):evaluate(p,{'warm':r},{},cfg)

    def test_old_exchange_update_is_metadata_under_new_protocol(self):
        cfg,p,r=self.sample();self.assertEqual(usable(r['book'],r['receipt'],1062,cfg),[])
        r['book']['exchange_at']=1100
        self.assertTrue(usable(r['book'],r['receipt'],1062,cfg))

    def test_missing_city_quote_and_future_signal_fail_closed(self):
        cfg,p,r=self.sample();g=dict(station='KNYC',date='2026-09-18',rules=[dict(slug='warm'),dict(slug='cold')])
        out=plan([g],cfg,{'warm':r});self.assertTrue(all(not a['selected'] for a in out['arms']))
        self.assertTrue(out['rejections'])

    def test_live_sized_entries_never_use_future_settlement_cash(self):
        cfg,p,r=self.sample()
        r['book']['offers'][0][1]=100
        entries={};payouts={};legs=[]
        for i in range(3):
            slug='warm'+str(i);o=deepcopy(p['arms'][0]['selected'][0]);o['slug']=slug;legs.append(o)
            raw=deepcopy(r);raw['book']['slug']=slug;entries[slug]=raw
            payouts[slug]=dict(response=dict(slug=slug,settlement='1'),receipt=dict(requested_at=2000,received_at=2001))
        p['arms'][0]['selected']=legs
        out=evaluate(p,entries,payouts,cfg)['results'][0]
        self.assertLessEqual(sum(D(row['price'])*D(row['quantity'])+D(row['fee']) for row in out['ledger'] if row['kind']=='buy'),10)
        self.assertGreaterEqual(min(D(row['cash']) for row in out['ledger']),40)

    def test_collector_lifecycle_and_interrupted_capture(self):
        import tempfile,json
        from pathlib import Path
        from unittest.mock import patch
        from tools import collect_us_multiband_forward as runner
        cfg,_,_=self.sample();cfg.update(signal_start=990,stop_at=2500,max_archive_bytes=1000000,
            groups=[dict(station='KNYC',date='2026-09-18',rules=[dict(slug='warm'),dict(slug='cold')])])
        def fake_get(path):
            slug=path.split('/')[-2]
            if path.endswith('settlement'):return dict(slug=slug,settlement=1 if slug=='warm' else 0),dict(requested_at=2000,received_at=2001)
            signal=clock[0]<1000;t=999 if signal else 1062;mid=.8 if slug=='warm' else .2
            raw=dict(marketData=dict(marketSlug=slug,state='MARKET_STATE_OPEN',transactTime='1970-01-01T00:16:39Z',
                bids=[dict(px=dict(currency='USD',value=str(mid-.02)),qty='100')],offers=[dict(px=dict(currency='USD',value=str(mid+.02)),qty='100')]))
            return raw,dict(requested_at=t-2,received_at=t,round_trip_seconds=2,public_cache_headers={'Date':formatdate(t,usegmt=True),'Age':'0'})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'registration.json').write_text(json.dumps(cfg));(root/'code-freeze.json').write_text(json.dumps({'sha256':{}}))
            clock=[995]
            with patch.object(runner.time,'time',side_effect=lambda:clock[0]),patch.object(runner,'get',side_effect=fake_get):
                self.assertEqual(runner.once(root)['phase'],'waiting_decision')
                clock[0]=1000;self.assertEqual(runner.once(root)['phase'],'waiting_entry')
                clock[0]=1060;self.assertEqual(runner.once(root)['phase'],'waiting_settlement')
                clock[0]=2000;self.assertEqual(runner.once(root)['phase'],'complete')
                self.assertTrue(all(r['positions']==0 for r in json.loads((root/'latest-result.json').read_text())['results']))
                (root/'state.json').write_text(json.dumps({'phase':'capturing_entry'}))
                self.assertEqual(runner.once(root)['phase'],'interrupted_capture')
