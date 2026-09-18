"""Executable multi-leg research strategies, with explicit settlement relationships.

No short selling, wallet methods, inferred semantic equivalence, or live orders.
Each proposed basket contains fully paid long tokens or a collateralized split.
"""
from dataclasses import dataclass, asdict
import math

STRATEGIES = {
    'yes-no-complement-arbitrage': ('binary', 'split'),
    'split-merge-redemption-arbitrage-ctf': ('binary', 'both'),
    'merge-split-set-completion-arbitrage': ('binary', 'both'),
    'gas-fee-threshold-arbitrage': ('binary', 'both'),
    'multi-outcome-overround-shorting-dutch-book-lay': ('partition', 'no'),
    'cross-market-mutually-exclusive-sum-over-one-fade': ('partition', 'no'),
    'count-bucket-ladder-arbitrage': ('count_partition', 'both'),
    'mutually-exclusive-first-to-ship-basket': ('partition', 'no'),
    'multi-outcome-awards-dutch-book-construction': ('partition', 'both'),
    'strike-ladder-monotonicity-arbitrage': ('threshold', 'pairs'),
    'temperature-band-ladder-coherence': ('temperature', 'both'),
    'nested-deadline-coherence-arbitrage': ('deadline', 'pairs'),
    'nominee-to-winner-conditional-coherence': ('implication', 'pairs'),
    'indication-nesting-coherence-on-approval-markets': ('implication', 'pairs'),
}

@dataclass(frozen=True)
class Costs:
    capital: float = 50.
    exposure: float = .15
    fee_bps: float = 100.
    slippage: float = .001
    fixed_cost: float = .05
    depth_fraction: float = .25
    minimum_net: float = .01
    max_age: float = 5.
    max_skew: float = 2.
    allow_unknown_age: bool = False

    def validate(self):
        for key, value in asdict(self).items():
            if key == 'allow_unknown_age':
                if type(value) is not bool: raise ValueError('allow_unknown_age must be boolean')
            elif type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('Costs must be finite numbers')
        if not 1 <= self.capital <= 100000 or not 0 < self.exposure <= .2:
            raise ValueError('Invalid capital or exposure')
        if not 0 <= self.fee_bps <= 1000 or not 0 <= self.slippage <= .05:
            raise ValueError('Invalid fee or slippage')
        if not 0 <= self.fixed_cost <= 10000 or not 0 <= self.minimum_net <= 1000:
            raise ValueError('Invalid fixed cost or minimum net')
        if not 0 < self.depth_fraction <= .25 or not 0 < self.max_age <= 30 or not 0 <= self.max_skew <= 5:
            raise ValueError('Invalid depth or timing limits')
        return self

def number(value, name):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError(name + ' must be a finite number')
    return value

def validate(document, cfg):
    cfg.validate()
    asof = number(document['asof'], 'asof')
    markets = document['markets']
    if not isinstance(markets, list) or not 1 <= len(markets) <= 32:
        raise ValueError('Require 1–32 markets')
    ids = set(); tokens = set(); stamps = []
    for m in markets:
        cid = m['condition']
        if not isinstance(cid, str) or not cid or cid in ids: raise ValueError('Duplicate or invalid condition')
        ids.add(cid)
        minimum = number(m['min_shares'], 'min_shares')
        if minimum <= 0: raise ValueError('Minimum shares must be positive')
        for side in ['yes', 'no']:
            q = m[side]
            token = q['token']
            if not isinstance(token, str) or not token or token in tokens: raise ValueError('Duplicate or invalid token')
            tokens.add(token)
            if q['condition'] != cid or q['outcome'] != side: raise ValueError('Token mapping mismatch')
            for key in ['bid', 'ask', 'bid_size', 'ask_size']: number(q[key], key)
            if not 0 <= q['bid'] < q['ask'] <= 1 or min(q['bid_size'], q['ask_size']) <= 0:
                raise ValueError('Invalid or crossed book')
            stamp = q.get('exchange_at')
            if stamp is None:
                if not cfg.allow_unknown_age: raise ValueError('Unknown exchange timestamp')
            else:
                number(stamp, 'exchange_at')
                if not 0 <= asof - stamp <= cfg.max_age: raise ValueError('Stale or future quote')
                stamps.append(stamp)
    if stamps and max(stamps) - min(stamps) > cfg.max_skew: raise ValueError('Asynchronous quote legs')
    return markets

def relation(document, required):
    r = document.get('relation', {})
    kind = r.get('kind')
    allowed = {'binary': {'binary'}, 'partition': {'partition'}, 'count_partition': {'count_partition'},
               'threshold': {'threshold'}, 'deadline': {'deadline'}, 'implication': {'implication'},
               'temperature': {'integer_partition', 'threshold'}}[required]
    if kind not in allowed: raise ValueError('Strategy requires relation: ' + ', '.join(sorted(allowed)))
    if kind == 'binary':
        if len(document['markets']) != 1: raise ValueError('Binary CTF requires exactly one condition')
        return r
    if not r.get('evidence') or r.get('verified') is not True:
        raise ValueError('Explicit relationship evidence and verified=true are required; market names are insufficient')
    if not r.get('definition_id'): raise ValueError('Shared settlement definition is required')
    if any(m.get('definition_id') != r['definition_id'] for m in document['markets']):
        raise ValueError('Every leg must reference the shared settlement definition')
    ids = [m['condition'] for m in document['markets']]
    if len(ids) < 2: raise ValueError('Multi-market relationship requires at least two conditions')
    if kind in ['partition', 'integer_partition', 'count_partition']:
        if r.get('exclusive') is not True or r.get('exhaustive') is not True:
            raise ValueError('Basket requires an exhaustive, mutually exclusive partition')
        if kind != 'partition':
            bands = r.get('bands', [])
            if len(bands) != len(ids) or [b['condition'] for b in bands] != ids:
                raise ValueError('One ordered band per condition is required')
            expected = 0 if kind == 'count_partition' else None
            for i, b in enumerate(bands):
                lo, hi = b['low'], b['high']
                if lo != expected: raise ValueError('Band gap, overlap, or missing lower tail')
                if (lo is not None and type(lo) is not int) or (hi is not None and type(hi) is not int):
                    raise ValueError('Band boundaries must be integers or null for infinite tails')
                if hi is None:
                    if i != len(bands)-1: raise ValueError('Upper tail must be last')
                elif lo is not None and hi < lo: raise ValueError('Reversed band')
                expected = None if hi is None else hi + 1
            if bands[-1]['high'] is not None: raise ValueError('Missing upper tail')
    elif kind in ['threshold', 'deadline']:
        values = r.get('values', [])
        if len(values) != len(ids): raise ValueError('One ordered threshold/deadline per condition is required')
        for v in values: number(v, 'threshold/deadline')
        if any(a >= b for a, b in zip(values, values[1:])): raise ValueError('Values must be strictly increasing')
        if kind == 'threshold' and r.get('operator') != '>=': raise ValueError('Threshold implementation requires >= semantics')
    else:
        if len(ids) != 2 or r.get('subset') not in ids or r.get('superset') not in ids or r['subset'] == r['superset']:
            raise ValueError('Implication requires distinct subset and superset conditions')
    return r

def basket(name, markets, sides, payout_floor, cfg, split=False, instant=False):
    legs = []
    for m, side in zip(markets, sides):
        q = m[side]
        price = max(0., q['bid'] - cfg.slippage) * (1 - cfg.fee_bps/10000) if split else (q['ask'] + cfg.slippage) * (1 + cfg.fee_bps/10000)
        legs.append(dict(condition=m['condition'],token=q['token'],side=side,action='sell_split_token' if split else 'buy',price=price,visible_size=q['bid_size'] if split else q['ask_size'],minimum=m['min_shares']))
    unit_cost = 1. if split else sum(x['price'] for x in legs)
    unit_receipt = sum(x['price'] for x in legs) if split else payout_floor
    budget = max(0., cfg.capital * cfg.exposure - cfg.fixed_cost)
    quantity = min(budget / max(unit_cost, 1e-12), *(x['visible_size'] * cfg.depth_fraction for x in legs))
    quantity = math.floor(quantity*1e6)/1e6
    net = quantity * (unit_receipt - unit_cost) - cfg.fixed_cost
    reason = None
    if quantity < max(x['minimum'] for x in legs): reason = 'below_venue_minimum_or_depth'
    elif net < cfg.minimum_net: reason = 'no_net_edge_after_costs'
    return dict(name=name,legs=legs,quantity=quantity,unit_cost=unit_cost,unit_receipt_floor=unit_receipt,
                required_capital=quantity*unit_cost+cfg.fixed_cost,net_floor=net,eligible=reason is None,
                rejection=reason,realized_pnl=None,instant_conversion=instant,
                payout_note='Immediate theoretical CTF conversion; no transaction simulated' if instant else 'Terminal floor conditional on the supplied settlement relationship; capital remains locked',
                execution_eligible=False)

def evaluate(strategy, document, costs=None):
    if strategy not in STRATEGIES: raise ValueError('Unknown coherence strategy')
    cfg=Costs(**(costs or {})).validate();markets=validate(document,cfg)
    required, mode = STRATEGIES[strategy];r=relation(document,required);kind=r['kind'];candidates=[]
    if kind == 'binary':
        if mode in ('both','split'): candidates.append(basket('Split collateral and sell YES + NO',markets*2,['yes','no'],1,cfg,split=True,instant=True))
        if mode == 'both': candidates.append(basket('Buy YES + NO and merge',markets*2,['yes','no'],1,cfg,instant=True))
    elif kind in ['partition','integer_partition','count_partition']:
        n=len(markets)
        if mode == 'both': candidates.append(basket('Buy exhaustive YES basket',markets,['yes']*n,1,cfg))
        candidates.append(basket('Buy exclusive NO basket',markets,['no']*n,n-1,cfg))
    else:
        pairs=[]
        if kind=='implication':
            lookup={m['condition']:m for m in markets};pairs=[(lookup[r['superset']],lookup[r['subset']])]
        else:
            for i,a in enumerate(markets):
                for b in markets[i+1:]:pairs.append((a,b) if kind=='threshold' else (b,a))
        for superset,subset in pairs:
            candidates.append(basket('Buy superset YES + subset NO',[superset,subset],['yes','no'],1,cfg))
    candidates.sort(key=lambda c:(c['eligible'],c['net_floor']),reverse=True)
    return dict(strategy=strategy,asof=document['asof'],kind=kind,costs=asdict(cfg),candidates=candidates,
                best=candidates[0] if candidates else None,execution_eligible=False,
                evidence=r.get('evidence','Same binary condition with checked YES/NO token mapping'),
                limitations=['Conditional mathematical bounds, not proof of fills or profit.',
                             'Simultaneous legs and displayed size are assumptions; legging risk remains.',
                             'Source descriptions contain errors; bid/ask directions and basket payoffs are corrected.',
                             'Relationship evidence is supplied input, not independently verified by this calculator.'])

def example(strategy):
    required,_=STRATEGIES[strategy];kind={'temperature':'integer_partition'}.get(required,required)
    count=1 if kind=='binary' else 3 if kind in ('partition','count_partition','integer_partition') else 2
    def quote(cid,side,p):return dict(condition=cid,token=cid+'-'+side,outcome=side,bid=max(.001,p-.02),ask=p,bid_size=100,ask_size=100,exchange_at=1000)
    markets=[]
    for i in range(count):
        cid='example-'+str(i);yes=.43 if count==1 else .30 if count==3 else .3 if i==0 else .7
        no=.45 if count==1 else .55 if count==3 else .7 if i==0 else .3
        markets.append(dict(condition=cid,definition_id='synthetic-common-definition',min_shares=1,yes=quote(cid,'yes',yes),no=quote(cid,'no',no)))
    ids=[m['condition'] for m in markets]
    r=dict(kind=kind,verified=True,evidence='Synthetic test fixture. No real market or realized return.',definition_id='synthetic-common-definition',exclusive=True,exhaustive=True)
    if kind in ['integer_partition','count_partition']:
        r['bands']=[dict(condition=ids[0],low=0 if kind=='count_partition' else None,high=9),dict(condition=ids[1],low=10,high=19),dict(condition=ids[2],low=20,high=None)]
    if kind in ['threshold','deadline']:r.update(values=[100,200],operator='>=')
    if kind=='implication':r.update(subset=ids[1],superset=ids[0])
    return dict(schema='polylab.coherence.v1',source='Synthetic example — not historical or live market data',asof=1000,markets=markets,relation=r)
