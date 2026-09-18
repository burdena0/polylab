"""Cost capacity and concentration diagnostics for an already audited US study."""
import hashlib
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def metrics(result, capital, default_station='KNYC'):
    entries = {r['slug']: r for r in result['ledger'] if r['kind'] == 'buy'}
    closed = [r for r in result['ledger'] if r['kind'] == 'settlement']
    pnl = Decimal(result['realized_pnl'])
    estimated_edge = sum((Decimal(str(t['probability']))*Decimal(t['quantity'])-
                          Decimal(t['price'])*Decimal(t['quantity'])-Decimal(t['fee'])
                          for t in entries.values()), Decimal(0))
    winners = sorted([Decimal(t['pnl']) for t in closed if Decimal(t['pnl']) > 0], reverse=True)
    duration = (result['period_end']-result['period_start'])/86400
    held_hours = [(t['t']-entries[t['slug']]['t'])/3600 for t in closed]
    return dict(station=result.get('station', default_station), strategy=result['strategy'], slippage_per_side=result['slippage_per_side'],
                entries=result['entries'], exits=result['exits'], realized_pnl=str(pnl),
                after_subscription=result['realized_after_subscription'], fees=result['fees'], open_basis=result['open_basis'],
                estimated_entry_edge_sum=str(estimated_edge), period_days=duration,
                estimated_entry_edge_per_day=float(estimated_edge)/duration,
                estimated_entry_edge_less_subscription=float(estimated_edge)-result['subscription_expense_prorated'],
                observed_trading_pnl_per_day=float(pnl)/duration,
                largest_winning_trade=str(winners[0]) if winners else '0',
                three_largest_winners=str(sum(winners[:3], Decimal(0))),
                pnl_without_largest_winner=str(pnl-(winners[0] if winners else Decimal(0))),
                average_closed_holding_hours=sum(held_hours)/len(held_hours) if held_hours else None,
                initial_capital=str(capital))


def main():
    directory = Path(sys.argv[1]).resolve()
    raw = (directory/'report.json').read_bytes()
    report = json.loads(raw)
    audit = json.loads((directory/'audit.json').read_text())
    digest = hashlib.sha256(raw).hexdigest()
    if audit['status'] != 'passed' or audit['report_sha256'] != digest:
        raise ValueError('Require an audit matching the unchanged report')
    default_station = 'Shared four-city account' if 'source_transfer' in report['registration'] else 'KNYC'
    rows = [metrics(r, report['registration']['capital'], default_station) for r in report['results']]
    output = dict(report_sha256=digest, rows=rows, limitations=[
        'Model-estimated entry edge is derived from unvalidated probabilities and assumed historical fills; it is neither realized profit nor an independently verified expectation.',
        'The estimated edge sums only executed scenario entries. Different arms can deploy different capital. No annualization or scale-up is implied.',
        'Removing the largest winner is a descriptive concentration check, not a replay with alternative cash availability.',
        'Each city/strategy/slippage row is a separate account; do not sum them into a portfolio.',
        'Trading P&L excludes external subscription, which is separately prorated over each entire registered test period.'])
    for name in ['edge-diagnostics.json', 'edge-diagnostics.md']:
        if (directory/name).exists():
            raise ValueError('Preserve existing diagnostics: '+name)
    money = lambda v: str(Decimal(str(v)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    lines = ['# US cost capacity and concentration', '',
             'These diagnostics use the audited report without changing its strategy or trades. Model-estimated edge is an unvalidated estimate; historical fills are assumed.', '',
             '| City | Strategy | Slip/side | Entries | Trading P&L | After subscription | Estimated entry edge total | P&L minus largest winner |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append('| '+ ' | '.join([r['station'], r['strategy'], r['slippage_per_side'], str(r['entries']),
                                      '$'+money(r['realized_pnl']), '$'+money(r['after_subscription']),
                                      '$'+money(r['estimated_entry_edge_sum']), '$'+money(r['pnl_without_largest_winner'])])+' |')
    lines += ['', *['- '+s for s in output['limitations']], '']
    (directory/'edge-diagnostics.json').write_text(json.dumps(output, indent=2))
    (directory/'edge-diagnostics.md').write_text('\n'.join(lines))
    print(json.dumps(dict(directory=str(directory), rows=rows), indent=2))


if __name__ == '__main__':
    main()
