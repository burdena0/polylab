"""Run and chart registered US shared-capital comparisons."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_portfolio import run


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime, timezone
    from decimal import Decimal, ROUND_HALF_UP
    dest, report = run(Path(sys.argv[1]).resolve(), ROOT, Path(sys.argv[2]).resolve())
    money = lambda value: str(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    colors = {'benter':'#245bdd','market_recalibrated':'#009c91','market_only':'#777','mos_only':'#d65c38'}
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=True)
    for column, slip in enumerate(report['registration']['slippage_per_side']):
        rows = [r for r in report['results'] if r['slippage_per_side']==slip]
        for row in rows:
            points = [dict(t=row['period_start'], realized_pnl=0)]+row['curve']+[dict(t=row['period_end'], realized_pnl=float(row['realized_pnl']))]
            dates = [datetime.fromtimestamp(p['t'], timezone.utc) for p in points]
            for i in range(2):
                end_value = row['realized_after_subscription'] if i else row['realized_pnl']
                style = dict(color=colors[row['strategy']], linestyle='--' if row['strategy']=='market_recalibrated' else '-',
                             label=row['strategy'].replace('_',' ')+' $'+money(end_value))
                if i:
                    # Expense accrues continuously; only settlements jump.
                    net_dates, net_values, previous = [], [], 0
                    for p in points:
                        cost = report['registration']['monthly_subscription']*(p['t']-row['period_start'])/(30*86400)
                        net_dates.extend([datetime.fromtimestamp(p['t'], timezone.utc)]*2)
                        net_values.extend([previous-cost, p['realized_pnl']-cost])
                        previous = p['realized_pnl']
                    axes[i,column].plot(net_dates, net_values, **style)
                else:
                    axes[i,column].step(dates, [p['realized_pnl'] for p in points], where='post', **style)
        for i in range(2):
            axes[i,column].set_title(('Trading P&L' if i==0 else 'After allocated subscription')+' · slip $'+slip+'/side', loc='left', weight='bold')
            axes[i,column].set_ylabel('USD')
            axes[i,column].grid(alpha=.2)
            axes[i,column].legend(fontsize=8)
            axes[i,column].xaxis.set_major_formatter(mdates.DateFormatter('%b %d', tz=timezone.utc))
            axes[i,column].tick_params(axis='x', rotation=25)
    for i in range(2):
        low = min(ax.get_ylim()[0] for ax in axes[i])
        high = max(ax.get_ylim()[1] for ax in axes[i])
        for ax in axes[i]:
            ax.set_ylim(low, high)
    fig.suptitle('PolyLab | One $50 account across four US cities per strategy', fontsize=16, weight='bold')
    fig.text(.07,.025,'$40 reserve, $5 entry cap, shared cash, current trading fees; $200/month overhead shown separately.\nNine dates per city, same calendar period as known NYC pilot. Display-price fills and depth unverified.\nOpen basis is reported separately in JSON; these curves show realized scenario P&L, not marked account equity.', fontsize=10, color='#555')
    fig.tight_layout(rect=[0,.11,1,.95])
    fig.savefig(dest/'portfolio-profit.png', dpi=150)
    plt.close(fig)
    print(json.dumps(dict(directory=str(dest), results=[{k:r[k] for k in ['strategy','slippage_per_side','entries','exits','realized_pnl','realized_after_subscription','open_basis']} for r in report['results']]), indent=2))


if __name__ == '__main__':
    main()
