"""Causal common-time multi-city allocation research. No execution client."""
import bisect, heapq, json, time
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from urllib.parse import urlparse, parse_qs
from .us_accounting import Account, number, conservative_taker_fee as fee
from .us_benter import digest
from .us_replay import normalize_history

def cents(value, rounding=ROUND_CEILING):
    return int((number(value)*100).to_integral_value(rounding=rounding))

def signal_options(group, cfg, slip):
    """Consume only quotes at or before the registered decision."""
    quotes = []
    for rule in group['rules']:
        points = group['histories'].get(rule['slug'], [])
        i = bisect.bisect_right([p['t'] for p in points], group['target'])-1
        if i < 0 or group['target']-points[i]['t'] > cfg['max_quote_age_seconds']:
            return [], 'Incomplete contemporaneous ladder'
        quotes.append(points[i])
    if cfg['model_asof'] >= group['target']: raise ValueError('Future model')
    weights = [max(p['mid'], 1e-6)**cfg['beta'] for p in quotes]
    total = sum(weights)
    options = []
    for rule, quote, weight in zip(group['rules'], quotes, weights):
        probability = weight/total
        for side, p, raw in [('long', probability, number(quote['ask'])), ('short', 1-probability, number(1)-number(quote['bid']))]:
            price = raw+number(slip)
            if not 0 < price < 1: continue
            for quantity in range(1, int(number(cfg['entry_budget'])/price)+1):
                cost = price*quantity+fee(price, quantity)
                if cost > number(cfg['entry_budget']): break
                expected = number(p)*quantity-cost
                if expected < number(cfg['min_expected_dollars']): continue
                options.append(dict(station=group['station'], date=group['date'], slug=rule['slug'], side=side,
                                    quantity=quantity, probability=p, expected=str(expected), cost_cents=cents(cost),
                                    signal_price=str(price), signal_t=group['target']))
    # Dominated options never improve expected dollars at a fixed budget.
    frontier, best = [], number(-1)
    for o in sorted(options, key=lambda o:(o['cost_cents'], -number(o['expected']), o['slug'], o['side'], o['quantity'])):
        if number(o['expected']) > best:
            frontier.append(o); best = number(o['expected'])
    return frontier, None if frontier else 'No positive expected dollars after costs'

def select(options_by_city, available, method):
    """Multiple-choice knapsack: at most one outcome/side per city."""
    budget = min(cents(available, ROUND_FLOOR), 500*len(options_by_city))
    if budget <= 0: return []
    cities = sorted(k for k,v in options_by_city.items() if v)
    if not cities: return []
    if method == 'equal_budget':
        limit = min(500, budget//len(cities)); result = []
        for city in cities:
            valid = [o for o in options_by_city[city] if o['cost_cents'] <= limit]
            if valid: result.append(max(valid, key=lambda o:number(o['expected'])))
        return result
    if method != 'expected_dollars': raise ValueError('Unknown allocation method')
    states = {0:(number(0), [])}
    for city in cities:
        next_states = dict(states)
        for spent, (ev, chosen) in states.items():
            for option in options_by_city[city]:
                new_cost = spent+option['cost_cents']
                if new_cost > budget: continue
                new_ev = ev+number(option['expected'])
                if new_cost not in next_states or new_ev > next_states[new_cost][0]:
                    next_states[new_cost] = (new_ev, chosen+[option])
        states, best = {}, number(-1)
        for cost in sorted(next_states):
            if next_states[cost][0] > best:
                states[cost] = next_states[cost]; best = next_states[cost][0]
    return max(states.items(), key=lambda item:(item[1][0], -item[0]))[1][1]

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
                options[g['station']], reason = signal_options(g, cfg, slip)
                mapping[g['station']] = g
                if reason: rejections.append(dict(t=t, station=g['station'], reason=reason))
            available = account.cash-account.reserve
            chosen = select(options, available, method)
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

def load(root, project):
    cfg = json.loads((root/'registration.json').read_text())
    rows = json.loads((project/cfg['forecast_rows']).read_text())['rows']
    rowmap = {(r['station'],r['date']):r for r in rows}
    groups, coverage, hashes = [], [], {}
    for g in cfg['groups']:
        histories, payouts = {}, {}
        for r in g['rules']:
            if (r['station'],r['date']) != (g['station'],g['date']): raise ValueError('Mixed event identity')
            for kind in ['history','settlement']:
                path = root/(r['market_id']+'-'+kind+'.json')
                hashes[path.name] = digest(path)
                doc = json.loads(path.read_text()); url = urlparse(doc['receipt']['url'])
                if url.scheme != 'https' or url.hostname != 'gateway.polymarket.us': raise ValueError('Wrong venue')
                if kind == 'history':
                    if url.path != '/v1/price-history' or parse_qs(url.query).get('symbol') != [r['slug']]: raise ValueError('History identity')
                    histories[r['slug']], _ = normalize_history(doc['response'], g['target']-1800, g['target']+2700)
                else:
                    if url.path != '/v1/markets/'+r['slug']+'/settlement' or doc['response'].get('slug') != r['slug']: raise ValueError('Settlement identity')
                    p = number(doc['response']['settlement'])
                    if not 0 <= p <= 1: raise ValueError('Payout range')
                    payouts[r['slug']] = p
        release = (datetime.fromisoformat(g['date'])+timedelta(days=1)).replace(hour=11,tzinfo=ZoneInfo('America/New_York')).timestamp()
        row = rowmap.get((g['station'],g['date']))
        if row: release = max(release, row['observation_issued_at'])
        entry = dict(**g, histories=histories, payouts=payouts, release=release)
        _, reason = signal_options(entry, cfg, '0')
        coverage.append(dict(station=g['station'], date=g['date'], complete_signal=reason!='Incomplete contemporaneous ladder', price_records=sum(len(p) for p in histories.values()), reason=reason))
        groups.append(entry)
    return cfg, groups, coverage, hashes

def run(root, project):
    freeze = json.loads((root/'code-freeze.json').read_text())
    for name, expected in freeze['sha256'].items():
        if digest(project/name) != expected: raise ValueError('Frozen input changed: '+name)
    cfg, groups, coverage, hashes = load(root, project)
    results = [simulate(groups,cfg,method,slip) for slip in cfg['slippage_per_side'] for method in cfg['strategies']]
    dest = root/('analysis-'+str(time.time_ns())); dest.mkdir()
    report = dict(created_at=time.time(), registration=cfg, registration_sha256=digest(root/'registration.json'), source_hashes=hashes, coverage=coverage, results=results, live_execution=False)
    (dest/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return dest, report
