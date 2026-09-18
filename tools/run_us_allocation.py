"""Evaluate frozen common-time allocation study and render profit curves."""
import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_allocation import run

def main():
    import matplotlib
    matplotlib.use('Agg'); matplotlib.rcParams['text.parse_math']=False
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime,timezone
    dest, report=run(Path(sys.argv[1]).resolve(),ROOT)
    fig,axs=plt.subplots(1,2,figsize=(13,5),sharey=True)
    for ax,slip in zip(axs,report['registration']['slippage_per_side']):
        for r in report['results']:
            if r['slippage_per_side']!=slip: continue
            pts=r['curve']; dates=[datetime.fromtimestamp(p['t'],timezone.utc) for p in pts]
            ax.step(dates,[p['realized_pnl'] for p in pts],where='post',label=r['strategy'].replace('_',' ')+f" ${float(r['realized_pnl']):.2f}")
        ax.axhline(0,color='#777',linewidth=.7);ax.grid(alpha=.2);ax.legend(fontsize=9)
        ax.set_title('Slippage per side: $'+slip);ax.set_ylabel('Realized scenario P&L (USD)')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d',tz=timezone.utc));ax.tick_params(axis='x',rotation=25)
    fig.suptitle('Five US cities | Common-time allocation | One $50 account per arm',weight='bold')
    fig.text(.06,.02,'$40 reserve; $5/city cap; fees included; $0 subscription. Known outcome dates: retrospective exploration.\nDisplayed prices do not establish historical depth or fills. Alternatives cannot be added together.',fontsize=10)
    fig.tight_layout(rect=[0,.10,1,.94]);fig.savefig(dest/'allocation-profit.png',dpi=150);plt.close(fig)
    print(json.dumps(dict(directory=str(dest),coverage=sum(c['complete_signal'] for c in report['coverage']),results=[{k:r[k] for k in ['strategy','slippage_per_side','realized_pnl','entries','exits','open_basis']} for r in report['results']]),indent=2))

if __name__=='__main__':main()
