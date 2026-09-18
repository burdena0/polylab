"""Paper-derived probability methods. No market access or order execution."""
import math
import numpy as np
from scipy.optimize import minimize, brentq
from scipy.special import expit, logsumexp

def probabilities(values):
    p=np.asarray(values,dtype=float)
    if p.ndim!=1 or len(p)<2 or not np.all(np.isfinite(p)) or np.any(p<=0) or np.any(p>=1):
        raise ValueError('Require at least two finite probabilities strictly between 0 and 1')
    return p/p.sum()

def odds_to_probabilities(odds, method='shin'):
    o=np.asarray(odds,dtype=float)
    if o.ndim!=1 or len(o)<2 or not np.all(np.isfinite(o)) or np.any(o<=1):raise ValueError('Decimal odds must exceed 1')
    q=1/o; book=float(q.sum())
    if method=='normalization':return dict(probabilities=(q/book).tolist(),booksum=book,z=None)
    if method!='shin':raise ValueError('Unknown odds method')
    if book<1-1e-10:raise ValueError('Shin bookmaker model requires booksum >= 1; underround is not bookmaker margin')
    if abs(book-1)<1e-10:return dict(probabilities=q.tolist(),booksum=book,z=0.0)
    def p(z):
        # Rationalized Eq. 3 avoids subtractive cancellation near z=1.
        a=q*q/book
        return 2*a/(np.sqrt(z*z+4*(1-z)*a)+z)
    z=float(brentq(lambda z:p(z).sum()-1,0,1-1e-10,xtol=1e-13))
    result=p(z)
    if abs(result.sum()-1)>1e-8 or np.any(result<0):raise ValueError('Shin did not converge')
    return dict(probabilities=result.tolist(),booksum=book,z=z)

def benter_combine(fundamental, public, alpha, beta):
    f=probabilities(fundamental);p=probabilities(public)
    if len(f)!=len(p) or not all(math.isfinite(x) for x in (alpha,beta)):raise ValueError('Invalid combination')
    score=alpha*np.log(f)+beta*np.log(p)
    return np.exp(score-logsumexp(score)).tolist()

def fit_benter(fundamental, public, outcomes):
    f=np.array([probabilities(p) for p in fundamental]);p=np.array([probabilities(p) for p in public]);y=np.asarray(outcomes,dtype=int)
    if f.shape!=p.shape or len(y)!=len(f) or len(y)<10 or np.any(y<0) or np.any(y>=f.shape[1]):raise ValueError('Insufficient or inconsistent calibration rows')
    def objective(w):
        z=w[0]*np.log(f)+w[1]*np.log(p)
        return float(np.mean(logsumexp(z,axis=1)-z[np.arange(len(y)),y]))
    fit=minimize(objective,[.5,.5],method='BFGS',options={'gtol':1e-7,'maxiter':400})
    if not np.isfinite(fit.fun) or (not fit.success and np.linalg.norm(fit.jac)>1e-4):raise ValueError('Benter optimizer failed')
    return dict(alpha=float(fit.x[0]),beta=float(fit.x[1]),calibration_rows=len(y),log_loss=float(fit.fun))

def fit_logistic(x,y):
    x=np.asarray(x,float);y=np.asarray(y,float)
    mean=x.mean(axis=0);scale=x.std(axis=0);scale=np.where(scale<1e-8,1,scale)
    z=np.column_stack([np.ones(len(x)),(x-mean)/scale])
    if len(set(y))!=2:raise ValueError('Training needs both outcomes')
    def obj(w):return float(np.mean(np.logaddexp(0,z@w)-y*(z@w))+.01*np.dot(w[1:],w[1:]))
    fit=minimize(obj,np.zeros(z.shape[1]),method='BFGS')
    if not fit.success and np.linalg.norm(fit.jac)>1e-4:raise ValueError('Fundamental fit failed')
    return dict(weights=fit.x.tolist(),mean=mean.tolist(),scale=scale.tolist())

def predict_logistic(model,x):
    z=np.r_[1,(np.asarray(x)-model['mean'])/model['scale']]
    return float(np.clip(expit(z@model['weights']),1e-6,1-1e-6))

def scores(predictions, outcomes):
    p=np.clip(np.asarray(predictions,float),1e-9,1-1e-9);y=np.asarray(outcomes,float)
    if not len(y):return None
    loss=float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p)))
    return dict(n=len(y),brier=float(np.mean((p-y)**2)),log_loss=loss,pseudo_r2=1-loss/math.log(2),accuracy=float(np.mean((p>=.5)==y)))

def fractional_kelly(bankroll,p,price,fraction=.1):
    if not all(math.isfinite(v) for v in [bankroll,p,price,fraction]) or bankroll<0 or not 0<p<1 or not 0<price<1 or not 0<=fraction<=1:raise ValueError('Invalid Kelly inputs')
    # Benter Eq. 5: (p/price - 1)/(1/price - 1) = (p-price)/(1-price).
    return bankroll*fraction*max(0,(p-price)/(1-price))

def avellaneda_stoikov(mid,inventory,variance,time_left,gamma=.1,k=150):
    if variance<0 or time_left<0 or gamma<=0 or k<=0:raise ValueError('Invalid quoting model')
    reservation=mid-inventory*gamma*variance*time_left
    spread=gamma*variance*time_left+2/gamma*math.log1p(gamma/k)
    return dict(bid=max(.001,min(.999,reservation-spread/2)),ask=max(.001,min(.999,reservation+spread/2)),reservation=reservation)

def event_ofi(prev,cur):
    """Cont et al. Eq. 2 at best bid/ask; sampled books are an approximation."""
    return ((cur['su'] if cur['bu']>=prev['bu'] else 0)-(prev['su'] if cur['bu']<=prev['bu'] else 0)
            -(cur['sau'] if cur['au']<=prev['au'] else 0)+(prev['sau'] if cur['au']>=prev['au'] else 0))
