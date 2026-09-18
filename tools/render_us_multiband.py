"""Render audited backtest curves, collapsing same-time accounting events."""
import json,hashlib,time,sys
from pathlib import Path
from datetime import datetime,timezone
import matplotlib
matplotlib.use('Agg');matplotlib.rcParams['text.parse_math']=False
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

root=Path(sys.argv[1]).resolve();source=root/'report.json';doc=json.loads(source.read_text());audit=json.loads((root/'audit.json').read_text())
assert audit['report_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
start=min(p['t'] for r in doc['results'] for p in r['curve']);end=max(p['t'] for r in doc['results'] for p in r['curve'])
dest=root/('render-'+str(time.time_ns()));dest.mkdir();fig,axs=plt.subplots(1,2,figsize=(11,4.8),sharey=True);rows=[]
for ax,slip in zip(axs,['0','.005']):
    for method,color,style in [('single_band','#173f75','-'),('multi_band','#ab630c','--')]:
        r=next(r for r in doc['results'] if r['strategy']==method and r['slippage_per_side']==slip)
        by_time={start:0}
        for p in r['curve']:by_time[p['t']]=p['realized_pnl']
        by_time[end]=float(r['realized_pnl']);points=sorted(by_time.items())
        rows.extend(dict(strategy=method,slippage=slip,t=t,realized_pnl=pnl) for t,pnl in points)
        ax.step([datetime.fromtimestamp(t,timezone.utc) for t,_ in points],[pnl for _,pnl in points],where='post',color=color,linestyle=style,label=method.replace('_',' ')+f" ${float(r['realized_pnl']):.2f}")
    ax.axhline(0,color='#666',linewidth=.7);ax.grid(alpha=.2);ax.legend(fontsize=10);ax.set_title('Added slippage: $'+slip);ax.set_ylabel('Scenario realized P&L (USD)')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d',tz=timezone.utc));ax.tick_params(axis='x',rotation=25)
fig.suptitle('Five-city backtest: one band versus multiple bands',fontweight='bold')
fig.text(.07,.025,'Lines overlap: identical selections and P&L. One $50 account per alternative; $40 reserve, $5/city cap.\nFees included, no subscription. Known outcomes; historical displayed-price fills are unverified.',fontsize=9)
fig.tight_layout(rect=[0,.12,1,.94]);fig.savefig(dest/'multi-band-profit.png',dpi=160);plt.close(fig)
(dest/'source.json').write_text(json.dumps(dict(source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),rows=rows,method='Last cumulative value per exact timestamp; common start/end. Removes zero-duration intermediate settlement bookkeeping spikes without changing PNL.'),indent=2),encoding='utf-8')
print(dest)
