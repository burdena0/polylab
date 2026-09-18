"""Portfolio controls with explicit units and caller-supplied point-in-time inputs.

These functions return proposed paper allocations, never exchange orders.
"""
from dataclasses import dataclass,asdict
import math
import numpy as np
from scipy.optimize import linprog,minimize
from .probability import fractional_kelly

STRATEGIES={
 'kelly-optimal-sizing':'kelly',
 'volatility-targeted-book-scaling':'volatility',
 'liquidity-adjusted-position-limits':'liquidity',
 'resolution-correlation-budgeted-sizing':'correlation',
 'scenario-stress-allocation-engine':'scenario',
 'cross-market-net-exposure-netting':'netting',
 'drawdown-circuit-breaker-governor':'drawdown',
 'gas-settlement-cost-aware-rebalancing-cadence':'cadence',
}

def scalar(x,name,low=0,high=1e15):
    if type(x) not in (int,float) or not math.isfinite(x) or not low<=x<=high:raise ValueError(f'Invalid {name}')
    return float(x)

def vector(x,name,low=-1e9,high=1e9):
    if not isinstance(x,list) or not 1<=len(x)<=64:raise ValueError(f'Invalid {name} dimension')
    return np.array([scalar(v,name,low,high) for v in x])

def covariance(values,n):
    c=np.array(values,dtype=float)
    if c.shape!=(n,n) or not np.all(np.isfinite(c)) or not np.allclose(c,c.T,atol=1e-12):raise ValueError('Covariance must be finite, square and symmetric')
    if np.linalg.eigvalsh(c).min() < -1e-10:raise ValueError('Covariance is not positive semidefinite')
    return c

def realized_covariance(observations,asof):
    """Aligned same-cadence simple price returns; future observations are rejected."""
    scalar(asof,'asof');t=vector([r['t'] for r in observations],'timestamps',0,1e15)
    if len(t)<3 or np.any(np.diff(t)<=0) or t[-1]>asof:raise ValueError('Need at least 3 ordered past observations')
    if np.max(np.diff(t))-np.min(np.diff(t))>1e-6:raise ValueError('Covariance observations must have equal cadence')
    prices=np.array([r['prices'] for r in observations],float)
    if prices.ndim!=2 or not 1<=prices.shape[1]<=32 or not np.all(np.isfinite(prices)) or np.any(prices<=0):raise ValueError('Invalid aligned prices')
    returns=np.diff(prices,axis=0)/prices[:-1]
    c=np.atleast_2d(np.cov(returns,rowvar=False,ddof=1))
    return dict(covariance=c.tolist(),observations=len(t),return_interval_seconds=float(t[1]-t[0]),asof=asof)

def kelly(d):
    cash=scalar(d['cash'],'cash');p=scalar(d['probability'],'probability',1e-9,1-1e-9);price=scalar(d['cost_per_share'],'cost per share',1e-9,1-1e-9)
    fraction=scalar(d.get('fraction',.1),'Kelly fraction',0,.25);cap=scalar(d['remaining_exposure'],'exposure');depth=scalar(d['available_shares'],'available shares');minimum=scalar(d['minimum_shares'],'minimum shares',1e-9)
    raw=fractional_kelly(cash,p,price,fraction);quantity=min(raw,cash,cap)/price;quantity=min(quantity,depth)
    accepted=quantity>=minimum
    return dict(raw_budget=raw,budget=quantity*price if accepted else 0,quantity=quantity if accepted else 0,rejection=None if accepted else 'Below venue minimum; Kelly size is not rounded upward')

def volatility(d):
    capital=scalar(d['capital'],'capital',1);budget=scalar(d['budget'],'budget',0,capital);target=scalar(d['target_volatility'],'target volatility',0,1)
    caps=vector(d['position_caps'],'position caps',0,capital);c=covariance(d['covariance'],len(caps));sigma=np.sqrt(np.diag(c))
    # Zero measured volatility is uncertainty, not infinite capacity.
    inv=np.divide(1,sigma,out=np.zeros_like(sigma),where=sigma>1e-9)
    x=np.minimum(caps,budget*inv/inv.sum()) if inv.sum() else np.zeros(len(caps))
    risk=math.sqrt(max(0,float(x@c@x)))/capital
    multiplier=min(1,target/risk) if risk>0 else 0
    x*=multiplier
    return dict(allocations=x.tolist(),cash_remaining=capital-float(x.sum()),portfolio_volatility=math.sqrt(max(0,float(x@c@x)))/capital,
                risk_contributions=(x*(c@x)).tolist(),zero_volatility_excluded=[int(i) for i in np.where(sigma<=1e-9)[0]],unit='Volatility over the supplied covariance interval; not annualized',note='Inverse-volatility initial weights, capped then scaled to portfolio target; caps/correlation can prevent equal contributions')

def liquidity(d):
    mid=scalar(d['mid'],'mid',1e-9,1-1e-9);band=scalar(d.get('band',.03),'depth band',0,.2);participation=scalar(d.get('participation',.1),'participation',0,.25)
    def depth(items,side):
        total=0;seen=set()
        for price,size in items:
            scalar(price,'price',0,1);scalar(size,'size');
            if price in seen:raise ValueError('Duplicate price level')
            seen.add(price)
            if (side=='bids' and mid-band<=price<=mid) or (side=='asks' and mid<=price<=mid+band):total+=size
        return total
    entry=depth(d['asks'],'asks');exit=depth(d['bids'],'bids');cap=min(entry,exit)*participation
    volume=d.get('recent_volume');note=None
    if volume is None:note='Recent volume unavailable; depth-only analytical limit'
    else:cap=min(cap,scalar(volume,'recent volume')*scalar(d.get('volume_fraction',.1),'volume fraction',0,.25))
    minimum=scalar(d['minimum_shares'],'minimum shares',1e-9)
    return dict(maximum_shares=cap if cap>=minimum else 0,raw_limit=cap,entry_depth=entry,exit_depth=exit,volume=volume,note=note,rejection=None if cap>=minimum else 'Insufficient depth or volume for minimum size')

def correlation(d):
    capital=scalar(d['capital'],'capital',1);budget=scalar(d['budget'],'budget',0,capital)
    edge=vector(d['expected_returns'],'expected returns',-1,100);n=len(edge);c=covariance(d['covariance'],n);caps=vector(d['position_caps'],'position caps',0,capital)
    if len(caps)!=n:raise ValueError('Position dimension mismatch')
    factors=np.array(d['factor_loadings'],float);fc=vector(d['factor_caps'],'factor caps',0,capital)
    if factors.shape!=(len(fc),n) or not np.all(np.isfinite(factors)):raise ValueError('Invalid factor matrix')
    # Gross absolute loadings prevent an unverified hedge from releasing capacity.
    gross=np.abs(factors);risk_aversion=scalar(d.get('risk_aversion',1),'risk aversion',1e-9,100)
    objective=lambda x: risk_aversion*float(x@c@x)/capital-float(edge@x)
    constraints=[{'type':'ineq','fun':lambda x:budget-x.sum()},{'type':'ineq','fun':lambda x:fc-gross@x}]
    fit=minimize(objective,np.zeros(n),bounds=[(0,float(v)) for v in caps],constraints=constraints,method='SLSQP',options={'ftol':1e-10,'maxiter':500})
    if not fit.success:raise ValueError('Allocation optimizer failed: '+fit.message)
    x=np.maximum(0,fit.x)
    if x.sum()>budget+1e-6 or np.any(gross@x>fc+1e-6):raise ValueError('Optimizer violated allocation constraints')
    return dict(allocations=x.tolist(),cash_remaining=capital-float(x.sum()),gross_factor_exposure=(gross@x).tolist(),signed_factor_exposure=(factors@x).tolist(),expected_pnl=float(edge@x),portfolio_std_dollars=math.sqrt(max(0,float(x@c@x))),note='Proposed holdings from cash, not an automatic rebalance. Expected returns and covariance are supplied estimates.')

def scenario(d):
    current=vector(d['current_scenario_pnl'],'scenario P&L');cost=vector(d['cost_per_share'],'cost',1e-9,1);n=len(cost)
    payoffs=np.array(d['payoffs'],float);maximum=vector(d['maximum_shares'],'maximum shares',0);minimum=vector(d['minimum_shares'],'minimum shares',0)
    if payoffs.shape!=(len(current),n) or not np.all(np.isfinite(payoffs)) or np.any(payoffs<0) or np.any(payoffs>1) or len(maximum)!=n or len(minimum)!=n:raise ValueError('Invalid scenario payoff mapping')
    budget=scalar(d['budget'],'budget');loss=scalar(d['maximum_loss'],'maximum loss');profit=payoffs-cost
    # Maximize the worst total P&L. A tiny spend penalty chooses the cheapest tied solution.
    a=np.vstack([np.c_[-profit,np.ones(len(current))],np.r_[cost,0.]])
    b=np.r_[current,budget]
    fit=linprog(np.r_[cost*1e-9,-1.],A_ub=a,b_ub=b,bounds=[(0,float(v)) for v in maximum]+[(-loss,None)],method='highs')
    if not fit.success:return dict(feasible=False,reason='No allocation satisfies every scenario loss limit',allocations=[0.]*n,current_worst=float(current.min()))
    x=fit.x[:-1];x=np.where(x+1e-8>=minimum,x,0);after=current+profit@x
    # Dropping an under-minimum hedge must not silently destroy the constraint.
    if after.min() < -loss-1e-7 or after.min()<current.min()-1e-7:
        return dict(feasible=False,reason='Venue minimums invalidate the continuous allocation',allocations=[0.]*n,current_worst=float(current.min()))
    return dict(feasible=True,allocations=x.tolist(),spend=float(cost@x),current_worst=float(current.min()),worst_after=float(after.min()),scenario_pnl=after.tolist(),note='Bounded only for the supplied scenarios. Missing scenarios, execution costs not in cost_per_share, and unfilled legs remain risks.')

def netting(d):
    positions=d['positions'];gross_cost=0.;net={};gross={}
    if not isinstance(positions,list) or len(positions)>128:raise ValueError('Invalid positions')
    for p in positions:
        qty=scalar(p['shares'],'shares');gross_cost+=scalar(p['locked_cost'],'locked cost')
        if not p.get('factor_loadings'):raise ValueError('Explicit factor mapping is required')
        for name,loading in p['factor_loadings'].items():
            delta=qty*scalar(loading,'factor loading',-1,1);net[name]=net.get(name,0)+delta;gross[name]=gross.get(name,0)+abs(delta)
    return dict(net_factor_shares=net,gross_factor_shares=gross,locked_cost=gross_cost,collateral_released=0,note='Factor offsets reduce modeled directional sensitivity, not the actual cash tied in separate contracts. No collateral is released without a verified conversion.')

@dataclass
class DrawdownGovernor:
    peak:float=0
    mode:str='normal'
    halted_at:float|None=None
    last_at:float=-1
    high_watermark:float=0

    def update(self,equity,at,soft=.08,hard=.15,cooldown=3600):
        scalar(equity,'equity');scalar(at,'time');scalar(soft,'soft threshold',0,1);scalar(hard,'hard threshold',0,1);scalar(cooldown,'cooldown',0)
        if soft>=hard or at<self.last_at:raise ValueError('Invalid threshold order or time reversal')
        self.last_at=at;self.high_watermark=max(self.high_watermark,equity);self.peak=max(self.peak,equity)
        dd=1-equity/self.peak if self.peak else 0
        flatten=False
        if self.mode=='halted':
            if at-self.halted_at>=cooldown:
                self.peak=equity;self.mode='reduced';self.halted_at=None
                return dict(mode=self.mode,size_multiplier=.5,drawdown=dd,flatten=False,cancel_entries=False,restarted_after_cooldown=True)
        elif dd>=hard:
            self.mode='halted';self.halted_at=at;flatten=True
        else:self.mode='reduced' if dd>=soft else 'normal'
        return dict(mode=self.mode,size_multiplier=0 if self.mode=='halted' else .5 if self.mode=='reduced' else 1,drawdown=dd,flatten=flatten,cancel_entries=self.mode=='halted',restarted_after_cooldown=False)

def drawdown(d):
    governor=DrawdownGovernor();rows=[]
    if not isinstance(d['observations'],list) or not 1<=len(d['observations'])<=10000:raise ValueError('Invalid equity observations')
    for row in d['observations']:rows.append(dict(at=row['at'],equity=row['equity'],**governor.update(row['equity'],row['at'],d.get('soft',.08),d.get('hard',.15),d.get('cooldown',3600))))
    return dict(states=rows,state=asdict(governor),note='Flatten and cancellation are paper intents, not confirmed fills. Cooldown re-entry resets the control peak; lifetime high watermark is retained.')

def cadence(d):
    reduction=scalar(d['risk_reduction_dollars'],'risk reduction');cost=scalar(d['total_cost'],'total cost');remaining=scalar(d['monthly_remaining'],'monthly budget');at=scalar(d['asof'],'asof');last=scalar(d['last_rebalance_at'],'last rebalance');interval=scalar(d['minimum_interval'],'minimum interval')
    if last>at:raise ValueError('Future rebalance timestamp')
    reason='Monthly cost budget exhausted' if cost>remaining else 'Wait to batch small changes' if at-last<interval else 'Risk improvement does not cover costs' if reduction<=cost else None
    return dict(allow=reason is None,reason=reason,net_risk_improvement=reduction-cost,cost=cost,monthly_remaining_after=remaining-cost if reason is None else remaining,note='Caller supplies risk reduction in dollars on the same horizon as costs. No schedule or transaction is created.')

FUNCTIONS={name:globals()[name] for name in STRATEGIES.values()}
def evaluate(strategy,document):
    if strategy not in STRATEGIES:raise ValueError('Unknown risk strategy')
    return dict(strategy=strategy,result=FUNCTIONS[STRATEGIES[strategy]](document),execution_eligible=False)

def example(strategy):
    kind=STRATEGIES[strategy]
    examples={
      'kelly':dict(cash=50,probability=.7,cost_per_share=.5,remaining_exposure=7.5,available_shares=100,minimum_shares=5,fraction=.1),
      'volatility':dict(capital=50,budget=7.5,target_volatility=.005,position_caps=[5,5],covariance=[[.01,.004],[.004,.04]]),
      'liquidity':dict(mid=.5,bids=[[.49,100],[.48,50],[.40,500]],asks=[[.51,120],[.52,70]],recent_volume=500,minimum_shares=5),
      'correlation':dict(capital=50,budget=7.5,expected_returns=[.1,.08],covariance=[[.01,.009],[.009,.01]],position_caps=[5,5],factor_loadings=[[1,1]],factor_caps=[6]),
      'scenario':dict(current_scenario_pnl=[-8,5],cost_per_share=[.1],payoffs=[[1],[0]],maximum_shares=[10],minimum_shares=[5],budget=1,maximum_loss=4),
      'netting':dict(positions=[dict(shares=10,locked_cost=4,factor_loadings={'same-outcome':1}),dict(shares=8,locked_cost=5,factor_loadings={'same-outcome':-1})]),
      'drawdown':dict(observations=[dict(at=i*600,equity=e) for i,e in enumerate([50,54,49,44,45,45,45,45,45,45,46])],soft=.08,hard=.15,cooldown=3600),
      'cadence':dict(risk_reduction_dollars=.8,total_cost=.25,monthly_remaining=2,asof=10000,last_rebalance_at=1000,minimum_interval=3600),
    }
    return dict(source='Synthetic input example, not historical portfolio results',document=examples[kind])
