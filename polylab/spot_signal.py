"""External spot-price probability models; no oracle equivalence is assumed."""
import bisect,math,json,hashlib,time
import numpy as np
import pyarrow.parquet as pq
from scipy.special import ndtr,logit
from .research import ROOT,features,prepare_models,simulate,Config
from .probability import fit_logistic,predict_logistic,fit_benter,scores

class SpotHistory:
    def __init__(self,path=None):
        self.path=path or ROOT/'data/spot/btcusdt-1m.parquet';self.rows=pq.read_table(self.path).to_pylist();self.opens=[r['open_at'] for r in self.rows];self.available=[r['close_at']+1 for r in self.rows];self.by_open={r['open_at']:r for r in self.rows}
    def feature(self,m):
        # Decision at +61s: the first one-minute candle closes at +60s, plus 1s availability lag.
        asof=m['start']+61;end=bisect.bisect_right(self.available,asof);past=self.rows[max(0,end-61):end];opening=self.by_open.get(m['start'])
        if opening is None or len(past)!=61 or asof-self.available[end-1]>2:return None
        if any(b['open_at']-a['open_at']!=60 for a,b in zip(past,past[1:])):return None
        closes=np.array([r['close'] for r in past]);returns=np.diff(np.log(closes));sigma=max(float(np.std(returns,ddof=1)),.0001)
        # A 2 bp basis-error floor acknowledges spot venue / oracle disagreement.
        horizon=(m['end']-asof)/60;denom=math.sqrt(sigma*sigma*horizon+.0002**2)
        z=math.log(closes[-1]/opening['open'])/denom;gaussian=float(np.clip(ndtr(z),1e-6,1-1e-6))
        short=float(np.std(returns[-10:],ddof=1))/sigma;momentum5=math.log(closes[-1]/closes[-6])/(sigma*math.sqrt(5));momentum15=math.log(closes[-1]/closes[-16])/(sigma*math.sqrt(15))
        volumes=np.array([r['volume'] for r in past]);vol_z=float((volumes[-1]-volumes[:-1].mean())/max(volumes[:-1].std(),1))
        f=features({**m,'start':m['start']+1})
        if f is None:return None
        f.update(vector=[z,short,momentum5,momentum15,vol_z],gaussian=gaussian,spot_latest_available=self.available[end-1],spot_open_reference=opening['open'],spot_price=float(closes[-1]),spot_sigma=sigma)
        return f

def fit(history,spot):
    _,train,cal,_=prepare_models(history)
    def convert(rows):
        result=[]
        for row in rows:
            f=spot.feature(row['market'])
            if f:result.append(dict(market=row['market'],features=f))
        return result
    train=convert(train);cal=convert(cal);cut=int(.6*len(cal));fit_cal=cal[:cut];threshold=fit_cal[-1]['market']['end']+86400;validation=[r for r in cal[cut:] if r['market']['start']>=threshold]
    if min(len(train),len(fit_cal),len(validation))<15:raise ValueError('Insufficient chronological external-signal samples')
    fundamental=fit_logistic([r['features']['vector'] for r in train],[r['market']['label'] for r in train])
    fp=[predict_logistic(fundamental,r['features']['vector']) for r in fit_cal];pub=[r['features']['public'] for r in fit_cal]
    blend=fit_benter([[p,1-p] for p in fp],[[p,1-p] for p in pub],[1-r['market']['label'] for r in fit_cal])
    model=dict(fundamental=fundamental,benter=blend)
    return model,train,fit_cal,validation

def replay(rows,model,kind,config=None):
    if kind=='gaussian':
        # Exact logit encoding lets the existing causal fill engine consume the closed-form probability.
        adapted=[dict(market=r['market'],features={**r['features'],'vector':[float(logit(r['features']['gaussian']))]}) for r in rows]
        m={'fundamental':{'weights':[0,1],'mean':[0],'scale':[1]}}
        return simulate(adapted,'fundamental',m,Config(**(config or {})))
    return simulate(rows,'benter' if kind=='benter' else 'fundamental',model,Config(**(config or {})))

def register():
    path=ROOT/'data/spot/model-registration.json'
    if path.exists():return json.loads(path.read_text())
    history=json.loads((ROOT/'data/prepared/history.json').read_text());spot=SpotHistory();model,train,cal,validation=fit(history,spot)
    results={kind:replay(validation,model,kind) for kind in ['gaussian','fundamental','benter']}
    # Selection uses only costed validation equity; win rate is not an objective.
    selected=max(results,key=lambda k:results[k]['net_pnl'])
    reg=dict(created_at=time.time(),model=model,selection_metric='Validation net P&L after costs, with unexited inventory marked zero',selected=selected,validation_results={k:{f:v[f] for f in ['trades','realized_pnl','net_pnl','open_basis']} for k,v in results.items()},samples=dict(train=len(train),combination_fit=len(cal),validation=len(validation)),validation_conditions=[r['market']['condition'] for r in validation],source_sha256=hashlib.sha256(spot.path.read_bytes()).hexdigest(),parameters=dict(decision_seconds=61,candle_availability_lag=1,volatility_minutes=60,minimum_minute_volatility=.0001,spot_oracle_basis_floor=.0002),note='Models use verified binary outcomes for training, but Binance spot is not Chainlink. No profit claim or live promotion.')
    path.write_text(json.dumps(reg,indent=2,allow_nan=False));return reg

if __name__=='__main__':print(json.dumps(register(),indent=2))
