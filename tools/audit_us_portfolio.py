"""Recompute portfolio allocation from audited per-city decisions and raw payouts."""
import hashlib, json, sys
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from tools.audit_us_transfer import audit as audit_transfer


def audit(directory):
    directory = Path(directory).resolve()
    report = json.loads((directory/'report.json').read_text())
    cfg = json.loads((directory.parent/'registration.json').read_text())
    source_analysis = Path(report['transfer_analysis'])
    source = source_analysis.parent
    source_audit = audit_transfer(source_analysis)
    transfer = json.loads((source_analysis/'report.json').read_text())
    checks = 0
    def require(condition, message):
        nonlocal checks
        if not condition: raise ValueError(message)
        checks += 1
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    require(report['registration'] == cfg, 'Portfolio registration differs')
    require(report['transfer_report_sha256'] == source_audit['report_sha256'], 'Transfer report changed')
    require(digest(source/'registration.json') == cfg['source_registration_sha256'], 'Transfer registration changed')
    require(report['source_hashes'] == transfer['source_hashes'], 'Portfolio uses different source receipts')
    for name, value in json.loads((directory.parent/'code-input-freeze.json').read_text())['sha256'].items():
        require(digest(ROOT/name) == value, 'Frozen input/code changed: '+name)
    amendment_path = directory.parent/'execution-amendment-v2.json'
    if amendment_path.exists():
        amendment = json.loads(amendment_path.read_text())
        for name, value in amendment['sha256'].items():
            require(digest(ROOT/name) == value, 'Amended adapter/code changed: '+name)
        require(amendment['created_at'] < report['created_at'], 'Execution fix registered after result')
    require(cfg['created_at'] < transfer['created_at'], 'Portfolio registered after transfer results')
    keys = [(r['strategy'], r['slippage_per_side']) for r in report['results']]
    require(len(keys) == len(set(keys)) and set(keys) == {(s,c) for s in cfg['strategies'] for c in cfg['slippage_per_side']}, 'Wrong comparison arms')
    require(report['coverage'] == transfer['coverage'], 'Coverage mismatch')
    rows = json.loads((ROOT/transfer['registration']['forecast_rows']).read_text())['rows']
    rowmap = {(r['station'],r['date']):r for r in rows}
    rules = {r['slug']:r for g in transfer['registration']['groups'] for r in g['rules']}
    D = lambda n: Decimal(str(n))
    fee = lambda p,q: (D('.0695')*p*q*(1-p)).quantize(D('.01'), rounding=ROUND_HALF_EVEN)
    summaries = []
    for result in report['results']:
        source_results = [r for r in transfer['results'] if r['strategy']==result['strategy'] and r['slippage_per_side']==result['slippage_per_side']]
        expected_diagnostics = [dict(station=r['station'],**d) for r in source_results for d in r['diagnostics']]
        require(result['diagnostics'] == expected_diagnostics, 'Portfolio decisions differ from frozen per-city signals')
        times, event_rows = [], []
        for diagnostic in expected_diagnostics:
            c = diagnostic['candidate']
            if c is None: continue
            p = D(c['price']); q = int(D(cfg['entry_budget'])/p)
            while q and p*q+fee(p,q)>D(cfg['entry_budget']): q -= 1
            if q == 0: continue
            edge = D(c['probability'])*q-p*q-fee(p,q)
            context = {**c, 'station':diagnostic['station'], 'date':diagnostic['date']}
            times.append((c['entry_t'],1,-edge,c['slug'],context))
            rule = rules[c['slug']]
            settlement = source/(rule['market_id']+'-settlement.json')
            if settlement.exists():
                value = json.loads(settlement.read_text())['response']
                require(value['slug']==c['slug'], 'Wrong settlement source')
                payout = D(value['settlement']) if c['side']=='long' else 1-D(value['settlement'])
                release = (datetime.fromisoformat(diagnostic['date'])+timedelta(days=1)).replace(hour=11,tzinfo=ZoneInfo('America/New_York')).timestamp()
                observation = rowmap.get((diagnostic['station'],diagnostic['date']))
                if observation: release = max(release,observation['observation_issued_at'])
                require(release>c['entry_t'], 'Invalid settlement chronology')
                times.append((release,0,D(0),c['slug'],{**context,'payout':payout}))
        cash, realized, paid, positions = D(cfg['capital']), D(0), D(0), {}
        expected_ledger = []
        for t, opening, _, slug, c in sorted(times):
            if opening:
                p = D(c['price']); budget = min(D(cfg['entry_budget']),cash-D(cfg['reserve'])); q = int(budget/p)
                while q and p*q+fee(p,q)>budget: q -= 1
                if not q or D(c['probability'])*q-p*q-fee(p,q)<D(transfer['registration']['min_expected_dollars']): continue
                charge = fee(p,q); basis = p*q+charge; cash -= basis; paid += charge
                positions[slug] = dict(q=q,basis=basis)
                expected_ledger.append(dict(kind='buy',slug=slug,t=t,price=str(p),quantity=str(q),fee=str(charge),cash=str(cash)))
            elif slug in positions:
                pos = positions.pop(slug); p = c['payout']; proceeds = p*pos['q']; gain = proceeds-pos['basis']; cash += proceeds; realized += gain
                expected_ledger.append(dict(kind='settlement',slug=slug,t=t,price=str(p),quantity=str(pos['q']),fee='0',cash=str(cash),pnl=str(gain)))
            require(cash>=D(cfg['reserve']), 'Shared reserve breached')
        require(len(expected_ledger)==len(result['ledger']), 'Skipped or extra portfolio trade')
        for expected, actual in zip(expected_ledger,result['ledger']):
            require(all(actual[k]==v if k in ['kind','slug','t'] else D(actual[k])==D(v) for k,v in expected.items()), 'Ledger allocation/fee/payout mismatch')
        basis = sum((p['basis'] for p in positions.values()),D(0))
        require(cash==D(result['cash']) and realized==D(result['realized_pnl']) and paid==D(result['fees']) and basis==D(result['open_basis']), 'Account totals mismatch')
        require(cash+basis==D(cfg['capital'])+realized, 'Conservation mismatch')
        buys = sum(t['kind']=='buy' for t in expected_ledger); exits = sum(t['kind']=='settlement' for t in expected_ledger)
        require(buys==result['entries'] and exits==result['exits'] and len(positions)==result['positions'], 'Counts mismatch')
        require(result['period_start']==min(r['period_start'] for r in source_results) and result['period_end']==max(r['period_end'] for r in source_results), 'Expense period mismatch')
        expense = cfg['monthly_subscription']*(result['period_end']-result['period_start'])/(30*86400)
        require(abs(expense-result['subscription_expense_prorated'])<1e-9 and abs(float(realized)-expense-result['realized_after_subscription'])<1e-9, 'Expense reconciliation mismatch')
        summaries.append(dict(strategy=result['strategy'],slippage=result['slippage_per_side'],entries=buys,exits=exits,realized=str(realized),cash=str(cash),open_basis=str(basis)))
    return dict(status='passed',checks=checks,transfer_checks=source_audit['checks'],report_sha256=digest(directory/'report.json'),results=summaries,
                scope='Independent allocation from audited frozen per-city candidates: simultaneous profit priority, global cash sequencing, whole quantities, fees, payouts, reserve, account totals and one subscription allocation per arm. Historical fills remain unverified.')


if __name__=='__main__':
    directory = Path(sys.argv[1]).resolve(); output = directory/'audit.json'
    if output.exists(): raise ValueError('Preserve prior audit')
    result = audit(directory); output.write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
