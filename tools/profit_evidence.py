"""Export an immutable research figure from actual backtests and forward paper state."""
import sys,json,time,hashlib,csv
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from polylab.research import ROOT

def run():
    root=ROOT/'data/profit-evidence';dest=root/str(time.time_ns());dest.mkdir(parents=True)
    source=ROOT/'data/profit-study-v1/runs/1789684510741440600/report.json';study=json.loads(source.read_text())
    paper=requests.get('http://127.0.0.1:8788/api/paper',timeout=10).json();accounts=[{k:v for k,v in paper.items() if k!='other_accounts'}]+paper['other_accounts']
    evidence=dict(created_at=time.time(),backtest_source=str(source),backtest_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),backtest=study,paper_accounts=accounts)
    (dest/'evidence.json').write_text(json.dumps(evidence,indent=2))
    names={'baseline':'Momentum baseline','liquidity':'Exit-depth cap','volatility':'Volatility cap','drawdown':'Drawdown governor','combined':'Combined controls','kelly_half':'Half Kelly (0 trades)'}
    colors={'baseline':'#315ba8','liquidity':'#bd7320','volatility':'#a65383','drawdown':'#777a31','combined':'#149092','kelly_half':'#777777'}
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#32363b','text.color':'#24282e'})
    fig=plt.figure(figsize=(15,10),facecolor='white');grid=fig.add_gridspec(2,2,height_ratios=[1.7,1],hspace=.52,wspace=.56);ax=fig.add_subplot(grid[0,:]);bars=fig.add_subplot(grid[1,0]);table=fig.add_subplot(grid[1,1]);table.axis('off')
    fig.suptitle('PolyLab | net profit evidence',x=.085,y=.975,ha='left',fontsize=23,fontweight='bold')
    fig.text(.085,.933,'1,200 previously unused BTC markets | May 7–18, 2026 | $50 per independent simulation',fontsize=12)
    styles={'baseline':'-','liquidity':'--','volatility':'-.','drawdown':':','combined':'-','kelly_half':'--'}
    for key,name in names.items():
        r=study['results'][key];curve=r['curve'];xs=[datetime.fromtimestamp(x['t'],timezone.utc) for x in curve];ys=[x['net_equity'] for x in curve]
        assert abs(ys[-1]-r['equity'])<1e-8
        assert abs(r['equity']-(50+r['realized_pnl']-r['open_basis']))<1e-8
        ax.step(xs,ys,where='post',label=name,color=colors[key],linestyle=styles[key],linewidth=2.5 if key=='combined' else 1.6)
    ax.set_ylabel('Simulated equity (USDC)');ax.set_ylim(30,52);ax.grid(axis='y',alpha=.2);ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d',tz=timezone.utc))
    ax.set_xticks([xs[0]]+[datetime(2026,5,d,tzinfo=timezone.utc) for d in [9,11,13,15,17]]+[xs[-1]])
    ax.set_xlim(xs[0],xs[-1]);ax.set_title('Equity after assumed fees, slippage, and depth limits',loc='left',pad=15,fontsize=14)
    ax.legend(loc='upper left',bbox_to_anchor=(0,-.13),ncol=3,frameon=False,fontsize=10)
    keys=sorted(names,key=lambda k:study['results'][k]['realized_pnl']);values=[study['results'][k]['realized_pnl'] for k in keys]
    bars.barh([names[k] for k in keys],values,color=[colors[k] for k in keys],height=.6);bars.axvline(0,color='#444',linewidth=.8);bars.set_xlim(-17,1);bars.set_xlabel('Realized backtest P&L (USDC)');bars.grid(axis='x',alpha=.15)
    for i,(key,value) in enumerate(zip(keys,values)):
        inside=value<=-7
        bars.text(value/2 if inside else value-.3,i,f'{value:+.2f}  ({study["results"][key]["trades"]} entries)',va='center',ha='center' if inside else 'right',fontsize=10,color='white' if inside else '#24282e')
    bars.set_title('Profit, not win rate',loc='left',fontsize=14,pad=12)
    captured=datetime.fromtimestamp(evidence['created_at'],timezone.utc).strftime('%b %d, %H:%M UTC')
    table.set_title('Forward paper snapshot · '+captured,loc='left',fontsize=13,pad=12)
    table.text(0,.87,'Account',fontweight='bold');table.text(.62,.87,'P&L',fontweight='bold');table.text(.85,.87,'Open',fontweight='bold')
    for i,a in enumerate(accounts):
        label='Benter' if a['strategy']=='benter' else 'Guide BTC' if a['strategy']=='guide-btc-momentum' else 'Momentum + depth' if a['risk_profile'] else 'Momentum baseline'
        y=.68-i*.17;table.text(0,y,label,fontsize=11);table.text(.62,y,f"{a['realized_pnl']:+.2f}",fontsize=11);table.text(.85,y,str(len(a['positions'])),fontsize=11)
    table.text(0,-.11,'New fee-curve accounts; snapshots are not fills.\nZero P&L does not establish a profitable strategy.',fontsize=10,color='#575c62',va='top')
    fig.text(.085,.034,'Backtest costs: assumed 100 bps per side + $0.001/share slippage. Historical fee schedules and exchange quote ages are unavailable.\nSame calendar regime as earlier research; simulated fills are not execution evidence. Current paper uses observed Gamma feeSchedule. No real trades.',fontsize=10,color='#575c62')
    fig.subplots_adjust(left=.16,right=.96,top=.865,bottom=.14);fig.savefig(dest/'profit-evidence.png',dpi=130);fig.savefig(dest/'profit-evidence.svg');plt.close(fig)
    with (dest/'results.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['variant','entries','realized_pnl','final_equity','open_basis','maximum_drawdown'])
        for k,r in study['results'].items():w.writerow([k,r['trades'],r['realized_pnl'],r['equity'],r['open_basis'],r['max_drawdown']])
    summary='\n'.join(f"| {names[k]} | {r['trades']} | ${r['realized_pnl']:+.2f} | ${r['equity']:.2f} |" for k,r in study['results'].items())
    (dest/'README.md').write_text(f'''# PolyLab profit evidence

No tested trading variant demonstrated positive net profit on this larger sample. The earlier exit-depth result of +$0.22 on 120 markets failed on 1,200 previously unused markets. The combined controls reduced losses but did not create an edge. Half Kelly made no trades.

![Equity and paper trading snapshot](profit-evidence.png)

| Variant | Entries | Realized P&L | Final equity |
|---|---:|---:|---:|
{summary}

The original study, source hash, full trade ledgers, all curves and paper snapshot are in `evidence.json`. These are independent $50 simulations, not a combined portfolio. Historical fee schedules and exchange timestamps are unknown; the old flat-fee results are preserved as assumption-based research. The new forward accounts use observed market fee curves. No live exchange orders are sent.

The external BTC Gaussian, logistic and Benter models also had negative validation P&L. They are not promoted, and their remaining test data has not been consumed for candidate selection.
''',encoding='utf-8')
    (root/'latest.json').write_text(json.dumps({'directory':str(dest),'created_at':evidence['created_at']}));print(dest)

if __name__=='__main__':run()
