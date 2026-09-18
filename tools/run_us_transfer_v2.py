"""Export all registered city transfer tests, including losing and missing cases."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_transfer_v2 import run

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime,timezone
    from decimal import Decimal,ROUND_HALF_UP
    dest,r=run(Path(sys.argv[1]).resolve(),ROOT)
    colors={'benter':'#245bdd','market_recalibrated':'#009c91','market_only':'#777','mos_only':'#d65c38'};names={'KMDW':'Chicago Midway','KLAX':'Los Angeles','KMIA':'Miami','KSFO':'San Francisco'}
    money=lambda v:str(Decimal(str(v)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
    for slip in r['registration']['slippage_per_side']:
        fig,axes=plt.subplots(2,2,figsize=(13,10),sharey=True)
        for station,ax in zip(r['registration']['stations'],axes.flat):
            rows=[x for x in r['results'] if x['station']==station and x['slippage_per_side']==slip]
            for row in rows:
                curve=[dict(t=row['period_start'],realized_pnl=0)]+row['curve']+[dict(t=row['period_end'],realized_pnl=float(row['realized_pnl']))]
                ax.step([datetime.fromtimestamp(p['t'],timezone.utc) for p in curve],[p['realized_pnl'] for p in curve],where='post',color=colors[row['strategy']],label=row['strategy'].replace('_',' ')+' $'+money(row['realized_pnl']),linestyle='--' if row['strategy']=='market_recalibrated' else '-')
            ax.set_title(names[station],loc='left',weight='bold');ax.set_ylabel('Trading scenario P&L (USD)');ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d',tz=timezone.utc));ax.tick_params(axis='x',rotation=25);ax.grid(alpha=.2);ax.legend(fontsize=8)
        fig.suptitle('PolyLab | Frozen US probability transfer · added slippage $'+slip+'/side',weight='bold',fontsize=15)
        fig.text(.07,.02,'Same NYC weights, four new cities; nine registered dates each, correlated calendar period.\nIndependent $50 accounts, $40 reserve. Display-price fills unverified; counterfactual current trading fees.\nCurves exclude external subscription. Full report includes $200/month allocated expense, open basis and every arm.',fontsize=10,color='#555')
        fig.tight_layout(rect=[0,.11,1,.95]);fig.savefig(dest/('transfer-profit.png' if slip=='0' else 'transfer-slippage.png'),dpi=150);plt.close(fig)
    r['runner_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();(dest/'report.json').write_text(json.dumps(r,indent=2));pointer=ROOT/'data/us-transfer-latest.json';tmp=pointer.with_suffix('.tmp');tmp.write_text(json.dumps(dict(directory=str(dest))));tmp.replace(pointer)
    print(json.dumps(dict(directory=str(dest),coverage=r['coverage'],results=[{k:x[k] for k in ['station','strategy','slippage_per_side','entries','exits','realized_pnl','realized_after_subscription','open_basis','mean_log_loss']} for x in r['results']]),indent=2))

if __name__=='__main__':main()
