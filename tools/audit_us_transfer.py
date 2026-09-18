"""Independent transfer-study ledger, source, partition and ablation audit."""
import hashlib
import json
import math
import sys
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT


def audit(analysis):
    analysis = Path(analysis).resolve()
    root = analysis.parent
    report = json.loads((analysis / 'report.json').read_text())
    cfg = json.loads((root / 'registration.json').read_text())
    checks = 0

    def require(condition, message):
        nonlocal checks
        if not condition:
            raise ValueError(message)
        checks += 1

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    freeze = json.loads((root / 'code-input-freeze.json').read_text())
    for name, expected in freeze['sha256'].items():
        require(digest(ROOT / name) == expected, 'Frozen input/code changed: ' + name)
    require(report['registration'] == cfg, 'Registration differs')
    require(report['registration_sha256'] == digest(root / 'registration.json'), 'Registration hash differs')
    source_hash = digest(root / 'frozen-source-report.json')
    require(source_hash == cfg['source_study_sha256'] == report['source_report_sha256'], 'NYC source differs')
    source = json.loads((root / 'frozen-source-report.json').read_text())
    model = report['combination_model']
    require(model == cfg['frozen_combination'] == source['combination_model'], 'Transfer weights refitted/changed')
    require(cfg['forecast_training'][1] < cfg['combination_training'][0] <= cfg['combination_training'][1] < cfg['test_dates'][0], 'Overlapping date partitions')
    require(all(cfg['combination_training'][0] <= d <= cfg['combination_training'][1] for d in model['dates']), 'Combination fit used test dates')
    require(report['forecast_rows_sha256'] == digest(ROOT / cfg['forecast_rows']), 'Forecast inputs changed')
    forecast_rows = json.loads((ROOT / cfg['forecast_rows']).read_text())['rows']
    for station in cfg['stations']:
        training = [r for r in forecast_rows if r['station'] == station and cfg['forecast_training'][0] <= r['date'] <= cfg['forecast_training'][1]]
        fitted = report['station_forecast_models'][station]
        require(len(training) >= 20 and len({r['date'] for r in training}) == len(training), 'Insufficient station training')
        require(fitted['training_sha256'] == hashlib.sha256(json.dumps(training, sort_keys=True).encode()).hexdigest(), 'Station training rows differ')
        require(fitted['last_training_date'] == max(r['date'] for r in training) <= cfg['forecast_training'][1], 'Station trained after cutoff')
        errors = [r['observed_high_f']-r['blend_high_f'] for r in training]
        bias = sum(errors)/len(errors)
        spread = max(1., math.sqrt(sum((e-bias)**2 for e in errors)/(len(errors)-1)))
        require(abs(fitted['bias_f']-bias) < 1e-10 and abs(fitted['residual_std_f']-spread) < 1e-10, 'Station calibration differs')
    for name, expected in report['source_hashes'].items():
        require(digest(root / name) == expected, 'Source changed: ' + name)
    for name, expected in report['code_sha256'].items():
        require(digest(ROOT / name) == expected, 'Analysis code changed: ' + name)
    amendment_path = root/'execution-amendment-v2.json'
    runner = 'tools/run_us_transfer.py'
    if amendment_path.exists():
        amendment = json.loads(amendment_path.read_text())
        for name, expected in amendment['sha256'].items():
            require(digest(ROOT/name) == expected, 'Amended adapter/code changed: '+name)
        require(amendment['created_at'] < report['created_at'], 'Execution fix registered after result')
        runner = amendment['transfer_runner']
    require(report['runner_sha256'] == digest(ROOT / runner), 'Runner changed')
    for name in report['source_hashes']:
        receipt = json.loads((root / name).read_text())['receipt']
        require(receipt['received_at'] >= cfg['created_at'], 'Response predates registration')
    expected_arms = {(s, a, c) for s in cfg['stations'] for a in cfg['strategies'] for c in cfg['slippage_per_side']}
    actual_arms = [(r['station'], r['strategy'], r['slippage_per_side']) for r in report['results']]
    require(len(actual_arms) == len(set(actual_arms)) and set(actual_arms) == expected_arms, 'Missing/duplicate/unregistered arm')
    groups = {(g['station'], g['date']): g for g in cfg['groups']}
    require(len(groups) == len(cfg['groups']) and all(g['role'] == 'test' for g in groups.values()), 'Duplicate or non-test group')
    require({(c['station'], c['date']) for c in report['coverage']} == set(groups), 'Incomplete coverage accounting')
    summaries = []
    for result in report['results']:
        station = result['station']
        rules = {r['slug']: r for (s, _), g in groups.items() if s == station for r in g['rules']}
        weights = result['combination_weights_used']
        expected_weights = ({'alpha': 0. if result['strategy'] == 'market_recalibrated' else model['alpha'], 'beta': model['beta']}
                            if result['strategy'] in ('benter', 'market_recalibrated') else None)
        require(weights == expected_weights, 'Incorrect ablation/baseline weights')
        require(model['asof'] < result['period_start'], 'Combination unavailable at decision')
        require(report['station_forecast_models'][station]['asof'] < result['period_start'], 'Station fit unavailable at decision')
        cash, realized, fees = Decimal(cfg['capital']), Decimal(0), Decimal(0)
        positions, last, buys, exits = {}, 0, 0, 0
        for trade in result['ledger']:
            require(trade['t'] >= last, 'Nonchronological ledger')
            last = trade['t']
            slug, p, q, fee = trade['slug'], Decimal(trade['price']), Decimal(trade['quantity']), Decimal(trade['fee'])
            require(slug in rules and q > 0 and q == int(q), 'Invalid contract/quantity')
            require(0 <= p <= 1, 'Invalid contract price')
            if trade['kind'] == 'buy':
                require(slug not in positions, 'Duplicate position')
                require(trade['t'] - trade['signal_t'] >= cfg['entry_delay_seconds'], 'Entry delay violated')
                expected_fee = (Decimal('.0695') * q * p * (1-p)).quantize(Decimal('.01'), rounding=ROUND_HALF_EVEN)
                require(fee == expected_fee, 'Fee mismatch')
                cost = q*p + fee
                require(cost <= Decimal(cfg['entry_budget']), 'Entry budget exceeded')
                require(Decimal(str(trade['probability']))*q-cost >= Decimal(cfg['min_expected_dollars']), 'Insufficient expected dollar edge')
                cash -= cost
                fees += fee
                positions[slug] = dict(basis=cost, q=q, side=trade['side'])
                buys += 1
            else:
                require(trade['kind'] == 'settlement' and slug in positions, 'Unexpected close')
                pos = positions.pop(slug)
                require(q == pos['q'] and fee == 0, 'Settlement quantity/fee mismatch')
                raw = json.loads((root / (rules[slug]['market_id'] + '-settlement.json')).read_text())['response']
                payout = Decimal(str(raw['settlement']))
                payout = payout if pos['side'] == 'long' else 1-payout
                require(raw['slug'] == slug and p == payout, 'Settlement identity/side mismatch')
                gain = q*p - pos['basis']
                require(gain == Decimal(trade['pnl']), 'Trade realized P&L mismatch')
                realized += gain
                cash += q*p
                exits += 1
            require(cash >= Decimal(cfg['reserve']) and cash == Decimal(trade['cash']), 'Reserve or cash mismatch')
        basis = sum((p['basis'] for p in positions.values()), Decimal(0))
        require(cash == Decimal(result['cash']) and realized == Decimal(result['realized_pnl']) and fees == Decimal(result['fees']) and basis == Decimal(result['open_basis']), 'Account summary mismatch')
        require(cash+basis == Decimal(cfg['capital'])+realized, 'Account conservation failed')
        require(buys == result['entries'] and exits == result['exits'] and len(positions) == result['positions'], 'Position/trade counts differ')
        expense = cfg['monthly_subscription'] * (result['period_end']-result['period_start']) / (30*86400)
        require(abs(expense-result['subscription_expense_prorated']) < 1e-9 and abs(float(realized)-expense-result['realized_after_subscription']) < 1e-9, 'Expense mismatch')
        scored, briers = [], []
        for diagnostic in result['diagnostics']:
            probs = diagnostic['probabilities']
            require(all(0 <= p <= 1 for p in probs) and abs(sum(probs)-1) < 1e-8, 'Invalid probability mass')
            group = groups[station, diagnostic['date']]
            payouts = [float(json.loads((root / (r['market_id']+'-settlement.json')).read_text())['response']['settlement']) for r in group['rules']]
            if all(p in (0., 1.) for p in payouts) and sum(payouts) == 1:
                y = payouts.index(1.)
                scored.append(-math.log(max(probs[y], cfg['probability_floor'])))
                briers.append(sum((p-int(i == y))**2 for i, p in enumerate(probs)))
        require(len(scored) == len(result['probability_scores']), 'Scored denominator differs')
        if scored:
            require(abs(sum(scored)/len(scored)-result['mean_log_loss']) < 1e-10, 'Log loss mismatch')
            require(abs(sum(briers)/len(briers)-result['mean_brier']) < 1e-10, 'Brier score mismatch')
        summaries.append(dict(station=station, strategy=result['strategy'], slippage=result['slippage_per_side'], entries=buys, exits=exits, realized=str(realized), cash=str(cash), open_basis=str(basis), scored_dates=len(scored)))
    return dict(status='passed', checks=checks, report_sha256=digest(analysis/'report.json'), results=summaries,
                scope='Frozen inputs, source receipts, chronology, complete registered arms, unchanged weights and alpha-only ablation, independent Decimal ledger/fees/settlements/reserve/expense and probability scores. Historical fills and forecast publication availability remain unverified.')


if __name__ == '__main__':
    path = Path(sys.argv[1]).resolve()
    output = path / 'audit.json'
    if output.exists():
        raise ValueError('Preserve existing audit')
    result = audit(path)
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
