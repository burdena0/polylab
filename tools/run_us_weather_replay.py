"""Run a completed frozen US weather pilot and export its profit evidence."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_weather_replay import run

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime,timezone
    history=Path(sys.argv[1]).resolve();calibration=Path(sys.argv[2]).resolve()
    if json.loads((history/'collection.json').read_text())['status']!='complete':raise ValueError('Finish the frozen historical sample before comparing strategies')
    dest,r=run(history,calibration)
    r['dependent_code_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['polylab/us_mos.py','polylab/us_accounting.py','polylab/us_replay.py','tools/run_us_weather_replay.py']}
    fig,(ax,table)=plt.subplots(2,1,figsize=(12,8),gridspec_kw={'height_ratios':[3,1.6]})
    colors={'mos_calibrated':'#245bdd','mos_uncorrected':'#c85a22','market_baseline':'#65727f'}
    first=r['period_start']
    for row in r['results']:
        curve=[dict(t=first,realized_pnl=0)]+row['curve']+[dict(t=r['period_end'],realized_pnl=float(row['realized_pnl']))]
        ax.step([datetime.fromtimestamp(p['t'],timezone.utc) for p in curve],[p['realized_pnl'] for p in curve],where='post',color=colors[row['strategy']],linestyle='--' if row['slippage_per_side']!='0' else '-',label=row['strategy'].replace('_',' ')+' / '+row['slippage_per_side'])
        peak=0.;drawdown=0.
        for p in curve:peak=max(peak,p['realized_pnl']);drawdown=max(drawdown,peak-p['realized_pnl'])
        row['realized_drawdown']=drawdown
    ax.axhline(0,color='#999',linewidth=.8);ax.set_title('PolyLab | US weather forecast replay',loc='left',weight='bold');ax.set_ylabel('Realized scenario P&L (USD)');ax.set_xlabel('2026 · UTC');ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d',tz=timezone.utc));ax.legend(fontsize=8,ncol=2);ax.grid(alpha=.2)
    table.axis('off');cells=[[x['strategy'].replace('_',' '),x['slippage_per_side'],str(x['entries']),f"${float(x['realized_pnl']):.2f}",f"${x['realized_after_subscription']:.2f}",f"${float(x['open_basis']):.2f}"] for x in r['results']]
    tab=table.table(cellText=cells,colLabels=['Strategy','Slippage/side','Entries','Trading P&L','After overhead','Open basis'],loc='center',cellLoc='center');tab.auto_set_font_size(False);tab.set_fontsize(9);tab.scale(1,1.6)
    fig.text(.06,.025,'Six NYC dates; current-fee counterfactual, assumed MOS availability and unverified historical fills.\nOverhead: prorated $200/month. Forecast skill and positive scenarios do not establish executable profit.',fontsize=10,color='#555');fig.tight_layout(rect=[0,.08,1,1]);fig.savefig(dest/'weather-profit.png',dpi=160);plt.close(fig)
    (dest/'report.json').write_text(json.dumps(r,indent=2));pointer=ROOT/'data/us-weather-replay-latest.json';tmp=pointer.with_suffix('.tmp');tmp.write_text(json.dumps({'directory':str(dest)}));tmp.replace(pointer)
    print(json.dumps(dict(directory=str(dest),coverage=r['coverage'],results=[{k:x[k] for k in ['strategy','slippage_per_side','entries','exits','realized_pnl','realized_after_subscription','open_basis','rejections']} for x in r['results']])))

if __name__=='__main__':main()
