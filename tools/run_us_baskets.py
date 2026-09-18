"""Export a registered US structural-inefficiency screen and costed scenario graph."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_baskets import run

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime,timezone
    dest,r=run(Path(sys.argv[1]).resolve(),ROOT)
    fig,(ax,table)=plt.subplots(2,1,figsize=(12,8),gridspec_kw={'height_ratios':[3,1.4]})
    for row in r['results']:
        curve=[dict(t=r['period_start'],realized_pnl=0)]+row['curve']+[dict(t=r['period_end'],realized_pnl=float(row['realized_pnl']))]
        ax.step([datetime.fromtimestamp(x['t'],timezone.utc) for x in curve],[x['realized_pnl'] for x in curve],where='post',label=row['strategy'].replace('_',' ')+' / '+row['slippage_per_side'],color='#245bdd' if row['strategy']=='buy_complete_ladder' else '#cf692d',linestyle='--' if row['slippage_per_side']!='0' else '-')
    ax.set_title('PolyLab | US ladder inefficiency test',loc='left',weight='bold');ax.set_ylabel('Realized scenario P&L (USD)');ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d',tz=timezone.utc));ax.grid(alpha=.2);ax.legend(fontsize=8)
    cells=[[x['strategy'].replace('_',' '),x['slippage_per_side'],x['initial_inefficiency_signals'],x['completed_basket_scenarios'],f"${float(x['realized_pnl']):.2f}",f"${x['realized_after_subscription']:.2f}"] for x in r['results']]
    table.axis('off');tab=table.table(cellText=cells,colLabels=['Basket','Slip/side','Signals','Completed scenarios','Trading P&L','After overhead'],loc='center',cellLoc='center');tab.auto_set_font_size(False);tab.set_fontsize(8);tab.scale(1,1.6)
    fig.text(.07,.025,'Nine registered NYC dates. Historical display-price scenario, not fill-verified arbitrage.\nAll legs must refresh after 60 seconds; maximum 10-second timestamp skew. Partial fills can lose money.\nCounterfactual current fees; external $200/month overhead; no margin optimization or live orders.',fontsize=9,color='#555');fig.tight_layout(rect=[0,.1,1,1]);fig.savefig(dest/'basket-profit.png',dpi=150);plt.close(fig)
    r['dependent_code_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['polylab/us_accounting.py','polylab/us_replay.py','polylab/weather_probability.py','tools/run_us_baskets.py']};(dest/'report.json').write_text(json.dumps(r,indent=2))
    pointer=ROOT/'data/us-baskets-latest.json';tmp=pointer.with_suffix('.tmp');tmp.write_text(json.dumps(dict(directory=str(dest))));tmp.replace(pointer)
    print(json.dumps(dict(directory=str(dest),coverage=r['coverage'],results=[{k:x[k] for k in ['strategy','slippage_per_side','initial_inefficiency_signals','completed_basket_scenarios','realized_pnl','realized_after_subscription','open_basis','rejections']} for x in r['results']]),indent=2))

if __name__=='__main__':main()
