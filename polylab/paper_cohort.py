"""Two independent paper accounts consuming exactly the same live observations."""
import json,time,threading
from .paper import PaperTrader
from .marketdata import btc_market,btc_tick
from .research import ROOT

class PaperCohort:
    def __init__(self):
        self.accounts=[PaperTrader('momentum-trend-following'),PaperTrader('momentum-trend-following',risk_profile='liquidity')]
        self.stop_event=threading.Event();self.thread=None;self.lock=threading.RLock();self.root=ROOT/'data/paper-cohort-fee-v2';self.root.mkdir(exist_ok=True)
        manifest=self.root/'registration.json'
        if not manifest.exists():manifest.write_text(json.dumps(dict(created_at=time.time(),accounts=[a.state['account_id'] for a in self.accounts],objective='Compare net realized P&L and locked basis on identical public data',fee_model='Observed Gamma feeSchedule at market discovery; no rebate credit',capital_per_account=50,live_execution=False),indent=2))
    def snapshots(self):return [a.snapshot() for a in self.accounts]
    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return self.snapshots()
            if any(a.state.get('coverage_failure_at') for a in self.accounts):raise ValueError('Cohort accounting failure requires review and a new versioned experiment')
            self.stop_event.clear()
            for a in self.accounts:
                with a.lock:a.state['running']=True;a.log('Paired paper study starting; both accounts share each recorded observation.');a.save()
            self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self.snapshots()
    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=20)
        return self.snapshots()
    def ingest(self,m,t):
        # Persist one shared observation before either account makes a decision.
        with (self.root/'observations.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(condition=m['condition'],**t))+'\n')
        try:
            for a in self.accounts:
                with a.lock:
                    a.step(m,t,{});a.state['snapshots']+=1;a.state['last_shared_observation']=t['t'];a.state['market']={k:v for k,v in m.items() if k!='ticks'};a.save()
        except Exception:
            # Persist any partial accounting, flag unequal coverage, and halt both arms.
            self.stop_event.set()
            for a in self.accounts:
                with a.lock:a.state['coverage_failure_at']=t['t'];a.log('Shared observation accounting failed; cohort halted for review.');a.save()
            raise
    def loop(self):
        current=None
        try:
            while not self.stop_event.is_set():
                try:
                    if current is None or time.time()>=current['end']:
                        current=btc_market(300)
                        if current:
                            with (self.root/'markets.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(current,allow_nan=False)+'\n')
                            current['ticks']=[]
                    if current is None:self.stop_event.wait(10);continue
                    tick=btc_tick(current);current['ticks'].append(tick);self.ingest(current,tick)
                except Exception as exc:
                    for a in self.accounts:
                        with a.lock:a.log('Paired public-data check: '+type(exc).__name__+': '+str(exc)[:100]);a.save()
                    self.stop_event.wait(5)
                self.stop_event.wait(1)
        finally:
            for a in self.accounts:
                with a.lock:a.state['running']=False;a.log('Paired paper worker stopped; balances and positions preserved.');a.save()
