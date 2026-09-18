"""Frozen archive screen and analytical cost sensitivity; never claims fills."""
import json,time,sys,hashlib
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.us_endgame import screen,economics
ROOT=Path(__file__).resolve().parents[1]

def main():
    source=Path(sys.argv[1]).resolve();cfg=json.loads((source/'registration.json').read_text())
    root=ROOT/'data/us-endgame'/str(time.time_ns());root.mkdir(parents=True)
    reports=sorted(source.glob('passes/*/report.json'));hashes={};rows=[];counts=Counter()
    for p in reports:
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        doc=json.loads(p.read_text())
        for q in doc['quotes']:
            raw_path=p.parent/q['receipt_file'];hashes[str(raw_path)]=hashlib.sha256(raw_path.read_bytes()).hexdigest()
            raw=json.loads(raw_path.read_text());result=screen(q['signal'],raw['book'],raw['receipt'],cfg)
            rows.append(dict(source=str(raw_path),**result));counts.update(result['reasons'])
    grid=[]
    for price in ['.50','.60','.70','.80','.85','.90','.95','.97','.99']:
        for slip in ['0','.005']:
            for probability in ['.90','.95','.99','1']:
                grid.append(dict(quoted_price=price,slippage=slip,**economics(price,100,slippage=slip,probability=probability)))
    report=dict(created_at=time.time(),source=str(source),passes=len(reports),quotes=len(rows),complete_day_quotes=sum(r['signal']['complete_day'] for r in rows),
        qualified_quotes=sum(r['research_qualified'] for r in rows),reasons=dict(counts),rows=rows,scenarios=grid,source_hashes=hashes,
        source_scope='Retrospective screen of prospective CLI receipts. Grid is analytic sensitivity, not backtest or paper profit.',
        fees_url='https://docs.polymarket.us/fees',initial_capital=50,reserve=40,entry_budget=5,monthly_subscription=0,
        assumptions='One aggregate fee bound, whole contracts, 25% displayed top depth; scenarios assume 100 displayed contracts. No exit fee at settlement. Unknown fill fragmentation, correction probability and payout delay.',
        positions=0,realized_profit=None,live_execution=False)
    (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    files=['polylab/us_endgame.py','tools/run_us_endgame.py','polylab/us_accounting.py','polylab/us_http_age.py']
    (root/'code-freeze.json').write_text(json.dumps({'sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}},indent=2),encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,5.8));colors=['#173f75','#ab630c','#545454','#728c24']
    for prob,color,style in zip(['.90','.95','.99','1'],colors,[':','--','-.','-']):
        subset=[x for x in grid if x['slippage']=='.005' and x['assumed_probability']==prob]
        ax.plot([float(x['quoted_price'])*100 for x in subset],[float(x['expected_profit']) for x in subset],color=color,linestyle=style,marker='o',label=f'{float(prob):.0%} assumed payout probability')
    ax.axhline(0,color='#222222',linewidth=1);ax.set(xlabel='Quoted contract price (cents)',ylabel='Expected net dollars per entry',title='Near-settlement cost sensitivity | $5 entry cap')
    ax.grid(alpha=.18);ax.legend(fontsize=9);fig.text(.12,.02,'Analytical scenarios, not realized profit. US taker fees + 0.5 cent slippage.\nWhole contracts; assumed 100 displayed depth; $50 account / $40 reserve.',fontsize=9)
    fig.tight_layout(rect=[0,.08,1,1]);fig.savefig(root/'cost-sensitivity.png',dpi=160);plt.close(fig)
    (ROOT/'data/us-endgame-latest.json').write_text(json.dumps({'directory':str(root)}),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['rows','scenarios','source_hashes']},indent=2));print(root)

if __name__=='__main__':main()
