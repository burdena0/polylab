"""Event-time replay for the multi-band comparison; separate immutable experiment."""
import bisect,heapq
from .us_accounting import Account,number,conservative_taker_fee as fee
from .us_multiband import signal_options as multi_options,select as multi_select
from .us_allocation import signal_options as single_options,select as single_select

def simulate(groups, cfg, method, slip):
    account = Account(cfg['capital'], cfg['reserve'])
    by_day = {}
    for g in groups: by_day.setdefault(g['target'], []).append(g)
    events, sequence = [], 0
    def push(t, priority, kind, payload):
        nonlocal sequence
        sequence += 1; heapq.heappush(events, (t, priority, sequence, kind, payload))
    for target, daily in sorted(by_day.items()): push(target, 1, 'decision', daily)
    decisions, rejections, curve = [], [], []
    while events:
        t, _, _, kind, payload = heapq.heappop(events)
        if kind == 'decision':
            options, mapping = {}, {}
            for g in payload:
                options[g['station']], reason = (multi_options if method == 'multi_band' else single_options)(g, cfg, slip)
                mapping[g['station']] = g
                if reason: rejections.append(dict(t=t, station=g['station'], reason=reason))
            available = account.cash-account.reserve
            chosen = multi_select(options, available, method) if method == 'multi_band' else single_select(options, available, 'expected_dollars')
            decisions.append(dict(t=t, available=str(available), eligible_cities=sum(bool(o) for o in options.values()), selected=chosen))
            for o in chosen:
                g = mapping[o['station']]; points = g['histories'][o['slug']]
                idx = bisect.bisect_left([p['t'] for p in points], t+cfg['entry_delay_seconds'])
                if idx == len(points) or points[idx]['t']-t-cfg['entry_delay_seconds'] > cfg['max_quote_age_seconds']:
                    rejections.append(dict(t=t, slug=o['slug'], reason='No delayed quote; no replacement')); continue
                push(points[idx]['t'], 2, 'entry', (o, points[idx], g))
        elif kind == 'entry':
            o, quote, g = payload
            price = (number(quote['ask']) if o['side']=='long' else number(1)-number(quote['bid']))+number(slip)
            budget = min(number(o['cost_cents'])/100, number(cfg['entry_budget']), account.cash-account.reserve)
            q = o['quantity']
            if not 0 < price < 1: q = 0
            while q and price*q+fee(price,q) > budget: q -= 1
            ev = number(o['probability'])*q-price*q-fee(price,q) if q else number(0)
            if not q or ev < number(cfg['min_expected_dollars']):
                rejections.append(dict(t=t, slug=o['slug'], reason='Delayed edge or budget failed; no replacement')); continue
            account.buy(o['slug'], price, q, t)
            account.ledger[-1].update(station=o['station'], date=o['date'], side=o['side'], signal_t=o['signal_t'], probability=o['probability'], expected_dollars=str(ev), planned_quantity=o['quantity'], planned_budget=str(budget))
            payout = g['payouts'].get(o['slug'])
            if payout is not None:
                if g['release'] <= t: raise ValueError('Settlement precedes entry')
                push(g['release'], 0, 'settle', (o, payout if o['side']=='long' else 1-payout))
        else:
            o, payout = payload
            account.close(o['slug'], payout, t, settlement=True)
            account.ledger[-1].update(station=o['station'], date=o['date'])
        s = account.snapshot()
        curve.append(dict(t=t, cash=float(s['cash']), realized_pnl=float(s['realized_pnl']), open_basis=float(s['open_basis'])))
    return dict(**account.snapshot(), strategy=method, slippage_per_side=slip, ledger=account.ledger,
                curve=curve, decisions=decisions, rejections=rejections, entries=sum(r['kind']=='buy' for r in account.ledger),
                exits=sum(r['kind']=='settlement' for r in account.ledger), monthly_subscription=0, fill_validated=False)
