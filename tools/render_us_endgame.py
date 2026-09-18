"""Render audited numeric scenario groups from an immutable report."""
import json,sys,hashlib,time
from pathlib import Path
from decimal import Decimal as D,ROUND_HALF_EVEN
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(sys.argv[1]).resolve();source=root/'report.json';report=json.loads(source.read_text());grid=report['scenarios'];checks=0
for r in grid:
    p=D(r['price']);q=r['quantity'];fee=(D('.0695')*q*p*(1-p)).quantize(D('.01'),rounding=ROUND_HALF_EVEN)
    assert D(r['fee'])==fee and D(r['cost'])==q*p+fee
    assert D(r['expected_profit'])==q*D(r['assumed_probability'])-D(r['cost'])
    assert D(r['conditional_win_profit'])==q-D(r['cost']) and D(r['cost'])<=5
    assert (q+1)*p+(D('.0695')*(q+1)*p*(1-p)).quantize(D('.01'),rounding=ROUND_HALF_EVEN)>5
    checks+=4
dest=root/('render-'+str(time.time_ns()));dest.mkdir()
fig,ax=plt.subplots(figsize=(9,5.8));colors=['#173f75','#ab630c','#545454','#728c24'];groups=[]
for prob,color,style in zip(['.90','.95','.99','1'],colors,[':','--','-.','-']):
    rows=[r for r in grid if D(r['slippage'])==D('.005') and D(r['assumed_probability'])==D(prob)]
    assert len(rows)==9;groups.append(dict(probability=prob,rows=rows))
    ax.plot([float(r['quoted_price'])*100 for r in rows],[float(r['expected_profit']) for r in rows],color=color,linestyle=style,marker='o',label=f'{float(prob):.0%} assumed payout probability')
ax.axhline(0,color='#222222',linewidth=1);ax.set(xlabel='Quoted contract price (cents)',ylabel='Expected net dollars per entry',title='Near-settlement cost sensitivity | $5 entry cap')
ax.grid(alpha=.18);ax.legend(fontsize=9)
fig.text(.12,.02,'Analytical scenarios, not realized profit. US taker fees + 0.5 cent slippage.\nWhole contracts; assumed 100 displayed depth; $50 account / $40 reserve.',fontsize=9)
fig.tight_layout(rect=[0,.08,1,1]);fig.savefig(dest/'cost-sensitivity.png',dpi=160);plt.close(fig)
(dest/'audit.json').write_text(json.dumps(dict(checks=checks,source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),groups=groups,amendment='Numeric grouping fixes omitted curves in original renderer; no scenario calculation changed.'),indent=2),encoding='utf-8')
print(json.dumps(dict(directory=str(dest),checks=checks,curves=len(groups))))
