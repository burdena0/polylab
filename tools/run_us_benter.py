"""Evaluate a registered US combination study and export a separate P&L graph."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_benter import run

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime,timezone
    dest,report=run(Path(sys.argv[1]).resolve(),ROOT)
    report['runner_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    fig,(ax,table)=plt.subplots(2,1,figsize=(13,10),gridspec_kw={'height_ratios':[3,2]})
    colors={'mos_only':'#d65c38','fixed_blend':'#008a83','benter':'#245bdd','market_only':'#727780','shin_asks':'#9b59b6'}
    for r in report['results']:
        curve=[dict(t=r['period_start'],realized_pnl=0)]+r['curve']+[dict(t=r['period_end'],realized_pnl=float(r['realized_pnl']))]
        ax.step([datetime.fromtimestamp(p['t'],timezone.utc) for p in curve],[p['realized_pnl'] for p in curve],where='post',color=colors[r['strategy']],linestyle='--' if r['slippage_per_side']!='0' else '-',label=r['strategy'].replace('_',' ')+' / '+r['slippage_per_side'])
        peak=0.;drawdown=0.
        for p in curve:peak=max(peak,p['realized_pnl']);drawdown=max(drawdown,peak-p['realized_pnl'])
        r['realized_drawdown']=drawdown
    ax.axhline(0,color='#999',linewidth=.8);ax.set_title('PolyLab | US forecast + market probability test',loc='left',weight='bold');ax.set_ylabel('Realized scenario P&L (USD)');ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d',tz=timezone.utc));ax.legend(fontsize=8,ncol=2);ax.grid(alpha=.2)
    cells=[[r['strategy'].replace('_',' '),r['slippage_per_side'],str(r['entries']),f"${float(r['realized_pnl']):.2f}",f"${r['realized_after_subscription']:.2f}",f"${float(r['open_basis']):.2f}"] for r in report['results']]
    table.axis('off');tab=table.table(cellText=cells,colLabels=['Strategy','Slippage/side','Entries','Trading P&L','After overhead','Open basis'],loc='center',cellLoc='center');tab.auto_set_font_size(False);tab.set_fontsize(9);tab.scale(1,1.6)
    model=report['combination_model'];fit_note=f"Combination fit: {model['calibration_dates']} dates, alpha={model['alpha']:.3f}, beta={model['beta']:.3f}." if model else 'Benter unavailable: '+str(report['fit_error'])+'.'
    fig.text(.065,.025,fit_note+'\nNine registered September dates; current-fee counterfactual, historical fills and publication timing unverified.\nExternal overhead: prorated $200/month. No live orders or forward-paper promotion.',fontsize=10,color='#555');fig.tight_layout(rect=[0,.09,1,1]);fig.savefig(dest/'benter-profit.png',dpi=150);plt.close(fig)
    (dest/'report.json').write_text(json.dumps(report,indent=2));pointer=ROOT/'data/us-benter-latest.json';tmp=pointer.with_suffix('.tmp');tmp.write_text(json.dumps(dict(directory=str(dest))));tmp.replace(pointer)
    print(json.dumps(dict(directory=str(dest),fit=report['combination_model'],fit_error=report['fit_error'],coverage=report['coverage'],results=[{k:r[k] for k in ['strategy','slippage_per_side','entries','exits','realized_pnl','realized_after_subscription','open_basis','mean_log_loss']} for r in report['results']]),indent=2))

if __name__=='__main__':main()
