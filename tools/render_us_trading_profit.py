"""Derived trading-only chart. Leaves audited source experiments unchanged."""
import json,sys,hashlib
from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP
from datetime import datetime,timezone
import matplotlib
matplotlib.use('Agg');matplotlib.rcParams['text.parse_math']=False
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def main():
    src=Path(sys.argv[1]);out=Path(sys.argv[2]);title=sys.argv[3]
    report=json.loads(src.read_text());fig,axes=plt.subplots(1,2,figsize=(13,5),sharey=True)
    common_end=max(p['t'] for r in report['results'] for p in r['curve'])
    for ax,slip in zip(axes,['0','.005']):
        for r in report['results']:
            if r['slippage_per_side']!=slip:continue
            points=r['curve']+[dict(t=common_end,realized_pnl=float(r['realized_pnl']))]
            if 'period_start' in r:points=[dict(t=r['period_start'],realized_pnl=0)]+points+[dict(t=r['period_end'],realized_pnl=float(r['realized_pnl']))]
            pnl=Decimal(r['realized_pnl']).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            ax.step([datetime.fromtimestamp(p['t'],timezone.utc) for p in points],[p['realized_pnl'] for p in points],where='post',linestyle='--' if r['strategy']=='market_recalibrated' else '-',label=r['strategy'].replace('_',' ')+f' ${pnl}')
        ax.set_title('Slippage per side: $'+slip);ax.grid(alpha=.2);ax.legend(fontsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d',tz=timezone.utc));ax.tick_params(axis='x',rotation=25);ax.set_ylabel('Realized scenario P&L (USD)')
    fig.suptitle(title,weight='bold');fig.text(.06,.02,'Fees included; $40 reserve; no subscription expense. Historical fills and depth unverified.\nKnown outcome dates: retrospective research. Comparison accounts are alternatives, not additive.',fontsize=10)
    fig.tight_layout(rect=[0,.10,1,.94]);out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(out,dpi=150);plt.close(fig)
    out.with_suffix('.source.json').write_text(json.dumps(dict(report=str(src.resolve()),sha256=hashlib.sha256(src.read_bytes()).hexdigest(),renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cost_policy='No configured subscription; trading results unchanged',rounding='Decimal half up, cents'),indent=2))

if __name__=='__main__':main()
