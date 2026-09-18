import tempfile,unittest,math
from pathlib import Path
import pyarrow as pa,pyarrow.parquet as pq
from polylab.spot_signal import SpotHistory

class SpotSignalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'candles.parquet';self.start=6000
        self.rows=[dict(open_at=i*60.,close_at=i*60+59.999999,open=60000.+i,high=60002.+i,low=59999.+i,close=60001.+i,volume=10.+i) for i in range(130)]
        self.m=dict(start=self.start,end=self.start+300,condition='test',ticks=[dict(t=self.start+i,bu=.49,au=.51,bd=.49,ad=.51,su=100,sau=100,sd=100,sad=100) for i in range(300)])
    def tearDown(self):self.temp.cleanup()
    def load(self):pq.write_table(pa.Table.from_pylist(self.rows),self.path);return SpotHistory(self.path)
    def test_future_candles_cannot_change_decision(self):
        first=self.load().feature(self.m);self.assertIsNotNone(first)
        for r in self.rows:
            if r['open_at']>self.start:r.update(close=90000.,volume=999999.)
        second=self.load().feature(self.m)
        self.assertEqual(first,second);self.assertLessEqual(first['spot_latest_available'],self.start+61)
    def test_missing_candle_rejects_feature(self):
        self.rows=[r for r in self.rows if r['open_at']!=self.start-60]
        self.assertIsNone(self.load().feature(self.m))
    def test_unavailable_first_candle_rejects_feature(self):
        for r in self.rows:
            if r['open_at']==self.start:r['close_at']=self.start+65
        self.assertIsNone(self.load().feature(self.m))

if __name__=='__main__':unittest.main()
