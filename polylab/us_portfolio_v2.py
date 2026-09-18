"""Chronological shared-capital US weather scenario; no execution client."""
import json
import time
from pathlib import Path
from .us_accounting import Account, number, conservative_taker_fee
from .us_benter import digest, probabilities_for
from .us_group_adapter import load_station_groups as load_groups
from .us_weather_replay import choose_entry


def allocate(candidates, cfg, start, end):
    account = Account(cfg['capital'], cfg['reserve'])
    events, rejected, curve = [], [], []
    if len({c['slug'] for c in candidates}) != len(candidates):
        raise ValueError('Repeated contract candidate')
    for c in candidates:
        price = number(c['price'])
        q = int(number(cfg['entry_budget'])/price)
        while q and price*q+conservative_taker_fee(price, q) > number(cfg['entry_budget']):
            q -= 1
        if not q:
            continue
        edge = number(c['probability'])*q-price*q-conservative_taker_fee(price, q)
        events.append((c['entry_t'], 1, -edge, c['slug'], c))
        if c['payout'] is not None:
            if c['release'] <= c['entry_t']:
                raise ValueError('Settlement precedes entry')
            events.append((c['release'], 0, number(0), c['slug'], c))
    for t, opening, _, slug, c in sorted(events):
        if opening:
            price = number(c['price'])
            available = min(number(cfg['entry_budget']), account.cash-account.reserve)
            q = int(available/price)
            while q and price*q+conservative_taker_fee(price, q) > available:
                q -= 1
            if not q:
                rejected.append(dict(slug=slug, station=c['station'], date=c['date'], reason='Shared cash reserve or whole-contract size'))
                continue
            expected = number(c['probability'])*q-price*q-conservative_taker_fee(price, q)
            if expected < number(cfg['min_expected_dollars']):
                rejected.append(dict(slug=slug, station=c['station'], date=c['date'], reason='Expected dollar edge below minimum after shared-cash sizing'))
                continue
            account.buy(slug, price, q, t)
            account.ledger[-1].update(side=c['side'], signal_t=c['signal_t'], probability=c['probability'], station=c['station'], date=c['date'])
        elif slug in account.positions:
            account.close(slug, c['payout'], t, settlement=True)
            account.ledger[-1].update(station=c['station'], date=c['date'])
        else:
            continue
        s = account.snapshot()
        curve.append(dict(t=t, realized_pnl=float(s['realized_pnl']), cash=float(s['cash']), open_basis=float(s['open_basis'])))
    result = account.snapshot()
    expense = cfg['monthly_subscription']*(end-start)/(30*86400)
    return dict(**result, ledger=account.ledger, curve=curve, rejections=rejected,
                entries=sum(t['kind']=='buy' for t in account.ledger), exits=sum(t['kind']=='settlement' for t in account.ledger),
                period_start=start, period_end=end, subscription_expense_prorated=expense,
                realized_after_subscription=float(result['realized_pnl'])-expense, fill_validated=False)


def simulate(groups, strategy, combination, cfg, slippage):
    model = {**combination, 'alpha': 0.} if strategy == 'market_recalibrated' else combination
    mode = 'benter' if strategy == 'market_recalibrated' else strategy
    candidates, diagnostics, rejected = [], [], []
    for g in groups:
        if g['role'] != 'test':
            raise ValueError('Portfolio requires test groups only')
        try:
            probs = probabilities_for(g, mode, model, cfg)
        except ValueError as exc:
            rejected.append(dict(station=g['station'], date=g['date'], reason=str(exc)))
            continue
        candidate, reason = choose_entry(g['rules'], dict(zip([r['market_id'] for r in g['rules']], probs)),
                                         g['histories'], g['target'], cfg['entry_delay_seconds'], cfg['max_quote_age_seconds'],
                                         cfg['entry_budget'], cfg['min_expected_dollars'], slippage)
        diagnostics.append(dict(station=g['station'], date=g['date'], probabilities=probs, candidate=candidate))
        if candidate is None:
            rejected.append(dict(station=g['station'], date=g['date'], reason=reason))
            continue
        payout = g['payouts'].get(candidate['slug'])
        if payout is not None and candidate['side'] == 'short':
            payout = 1-payout
        candidates.append(dict(**candidate, station=g['station'], date=g['date'], release=g['release'], payout=payout))
    result = allocate(candidates, cfg, min(g['target'] for g in groups), max(g['release'] for g in groups))
    result['rejections'] = rejected+result['rejections']
    result.update(strategy=strategy, slippage_per_side=slippage, diagnostics=diagnostics,
                  combination_weights_used={k:model[k] for k in ['alpha','beta']} if mode=='benter' else None)
    return result


def run(directory, project, transfer_analysis):
    root, project, source_analysis = Path(directory), Path(project), Path(transfer_analysis)
    registration = json.loads((root/'registration.json').read_text())
    source = project/registration['source_transfer']
    if source.resolve() != source_analysis.resolve().parent:
        raise ValueError('Wrong transfer study')
    if digest(source/'registration.json') != registration['source_registration_sha256']:
        raise ValueError('Transfer registration changed')
    freeze = json.loads((root/'code-input-freeze.json').read_text())
    for name, expected in freeze['sha256'].items():
        if digest(project/name) != expected:
            raise ValueError('Frozen portfolio code/input changed: '+name)
    report = json.loads((source_analysis/'report.json').read_text())
    audit = json.loads((source_analysis/'audit.json').read_text())
    if audit['status'] != 'passed' or audit['report_sha256'] != digest(source_analysis/'report.json'):
        raise ValueError('Transfer requires matching completed audit')
    if registration['created_at'] >= report['created_at']:
        raise ValueError('Portfolio registration must precede transfer results')
    cfg = report['registration']
    for key in ['strategies','slippage_per_side','capital','reserve','entry_budget','monthly_subscription']:
        if cfg[key] != registration[key]:
            raise ValueError('Portfolio changes frozen strategy/risk inputs: '+key)
    rows = json.loads((project/cfg['forecast_rows']).read_text())['rows']
    groups, coverage, hashes = [], [], {}
    for station in cfg['stations']:
        subset = {**cfg, 'station':station, 'groups':[g for g in cfg['groups'] if g['station']==station]}
        loaded, covered, receipts = load_groups(source, subset, rows, report['station_forecast_models'][station])
        groups.extend(loaded)
        coverage.extend(dict(station=station, **c) for c in covered)
        hashes.update(receipts)
    if hashes != report['source_hashes']:
        raise ValueError('Transfer receipts changed')
    results = [simulate(groups, strategy, report['combination_model'], cfg, slip)
               for slip in cfg['slippage_per_side'] for strategy in cfg['strategies']]
    dest = root/('analysis-'+str(time.time_ns()))
    dest.mkdir()
    output = dict(created_at=time.time(), registration=registration, venue='polymarket_us', coverage=coverage,
                  transfer_analysis=str(source_analysis.resolve()), transfer_report_sha256=digest(source_analysis/'report.json'),
                  source_hashes=hashes, results=results, live_execution=False,
                  limitations=['One $50 account per comparison arm across all four cities, with $40 cash reserve and at most $5 per entry. Arms are alternatives, not additive.',
                               'Same calendar period as the known NYC pilot; cross-city dependence remains. Registered during collection before new-city profitability was computed.',
                               'Chronological cash allocation can reject later signals or resize entries. Future proceeds and later quotes are unavailable to earlier entries.',
                               'Historical display-price fills and depth are unverified; September 17 fees are applied counterfactually.',
                               'No refitted coefficients, no live orders and no promotion into frozen forward accounts.'])
    (dest/'report.json').write_text(json.dumps(output, indent=2))
    return dest, output
