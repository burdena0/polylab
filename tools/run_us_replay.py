"""Run and plot a frozen US display-price feasibility sample."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_replay import run

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime,timezone
    source=Path(sys.argv[1]).resolve();dest,report=run(source)
    report['code_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['polylab/us_replay.py','polylab/us_accounting.py','tools/run_us_replay.py']}
    fig,(ax,table)=plt.subplots(2,1,figsize=(11,7),gridspec_kw={'height_ratios':[3,1.4]})
    colors={'momentum':'#2355dc','mean_reversion':'#ba4b20'}
    for row in report['results']:
        x=[datetime.fromtimestamp(p['t'],timezone.utc) for p in row['curve']];y=[p['realized_pnl'] for p in row['curve']]
        ax.step(x,y,where='post',color=colors[row['strategy']],linestyle='--' if row['slippage_per_side']!='0' else '-',label=f"{row['strategy'].replace('_',' ')} / slippage ${row['slippage_per_side']}")
    ax.axhline(0,color='#999',lw=.8);ax.set_ylabel('Realized trading P&L (USD)');ax.set_title('PolyLab | Polymarket US feasibility replay',loc='left',weight='bold');ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M',tz=timezone.utc));ax.set_xlabel('September 17, 2026 · UTC');ax.grid(alpha=.2);ax.legend(fontsize=9)
    table.axis('off')
    rows=[[r['strategy'].replace('_',' '),r['slippage_per_side'],f"{r['entries']} / {r['exits']}",f"${float(r['realized_pnl']):.2f}",f"${float(r['open_basis']):.2f}",f"${r['realized_after_prorated_subscription']:.2f}"] for r in report['results']]
    tab=table.table(cellText=rows,colLabels=['Strategy','Slippage/side','Entries / exits','Realized P&L','Open basis','After overhead*'],loc='center',cellLoc='center');tab.auto_set_font_size(False);tab.set_fontsize(9);tab.scale(1,1.7)
    fig.text(.07,.03,'Display-price scenarios, not verified fills. Open basis is reported separately.\n*Prorated $200/month subscription; no independent holdout or demonstrated profit.',fontsize=10,color='#555')
    fig.tight_layout(rect=[.02,.09,.98,.99]);fig.savefig(dest/'realized-pnl.png',dpi=160);plt.close(fig)
    (dest/'report.json').write_text(json.dumps(report,indent=2))
    pointer=ROOT/'data/us-replay-latest.json';tmp=pointer.with_suffix('.tmp');tmp.write_text(json.dumps({'directory':str(dest)}));tmp.replace(pointer)
    print(json.dumps({'directory':str(dest),'results':[{k:r[k] for k in ['strategy','slippage_per_side','entries','exits','realized_pnl','open_basis','fees','realized_after_prorated_subscription']} for r in report['results']]}))

if __name__=='__main__':main()
