"""Independently reconcile a completed US combination report against its receipts."""
import sys,json,hashlib,math
from decimal import Decimal,ROUND_HALF_EVEN
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT

def check(condition,message):
    if not condition:raise ValueError(message)

def main():
    analysis=Path(sys.argv[1]).resolve();root=analysis.parent;report=json.loads((analysis/'report.json').read_text());cfg=json.loads((root/'registration.json').read_text());frozen=json.loads((root/'input-code-freeze.json').read_text());checks=0
    for name,expected in frozen['sha256'].items():
        check(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,'Frozen input/code changed: '+name);checks+=1
    check(report['registration']==cfg,'Report registration mismatch')
    check(cfg['forecast_training'][1]<cfg['combination_training'][0]<=cfg['combination_training'][1]<cfg['test_dates'][0],'Overlapping partitions')
    for name,expected in report['source_hashes'].items():
        check(hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,'Source changed: '+name);checks+=1
    model=report['combination_model']
    if model:
        check(model['calibration_dates']>=cfg['minimum_combination_dates'],'Insufficient combination data')
        check(all(cfg['combination_training'][0]<=d<=cfg['combination_training'][1] for d in model['dates']),'Fit used test dates')
    test_rules={r['slug']:r for g in cfg['groups'] if g['role']=='test' for r in g['rules']};summaries=[]
    for result in report['results']:
        cash=Decimal(cfg['capital']);realized=Decimal(0);fees=Decimal(0);positions={};last=0;buys=0;exits=0
        for trade in result['ledger']:
            check(trade['t']>=last,'Ledger time moved backwards');last=trade['t'];slug=trade['slug'];check(slug in test_rules,'Trade outside test split');p=Decimal(trade['price']);q=Decimal(trade['quantity']);fee=Decimal(trade['fee'])
            check(q>0 and q==int(q),'Non-whole quantity')
            if trade['kind']=='buy':
                check(slug not in positions,'Duplicate position');check(trade['t']-trade['signal_t']>=cfg['entry_delay_seconds'],'Entry delay violated')
                expected_fee=(Decimal('.0695')*q*p*(1-p)).quantize(Decimal('.01'),rounding=ROUND_HALF_EVEN)
                check(fee==expected_fee,'Fee mismatch');cost=p*q+fee;check(cost<=Decimal(cfg['entry_budget']),'Entry budget exceeded');cash-=cost;fees+=fee;positions[slug]=dict(basis=cost,q=q,side=trade['side']);buys+=1
            else:
                check(trade['kind']=='settlement' and slug in positions,'Unexpected close');pos=positions.pop(slug);check(q==pos['q'] and fee==0,'Settlement quantity/fee mismatch')
                rule=test_rules[slug];source=json.loads((root/(rule['market_id']+'-settlement.json')).read_text())['response'];payout=Decimal(str(source['settlement']));payout=payout if pos['side']=='long' else 1-payout
                check(source['slug']==slug and p==payout,'Settlement source/side mismatch');gain=q*p-pos['basis'];check(gain==Decimal(trade['pnl']),'Realized trade P&L mismatch');realized+=gain;cash+=q*p;exits+=1
            check(cash>=Decimal(cfg['reserve']),'Cash reserve breached');check(cash==Decimal(trade['cash']),'Ledger cash mismatch');checks+=1
        basis=sum((p['basis'] for p in positions.values()),Decimal(0))
        check(cash==Decimal(result['cash']) and realized==Decimal(result['realized_pnl']) and fees==Decimal(result['fees']) and basis==Decimal(result['open_basis']),'Account summary mismatch')
        check(cash+basis==Decimal(cfg['capital'])+realized,'Account conservation failed')
        check(buys==result['entries'] and exits==result['exits'] and len(positions)==result['positions'],'Trade/position counts mismatch')
        expense=cfg['monthly_subscription']*(result['period_end']-result['period_start'])/(30*86400)
        check(abs(expense-result['subscription_expense_prorated'])<1e-9 and abs(float(realized)-expense-result['realized_after_subscription'])<1e-9,'Expense reconciliation failed')
        scored=[]
        for diagnostic in result['diagnostics']:
            probs=diagnostic['probabilities'];check(all(0<=p<=1 for p in probs) and abs(sum(probs)-1)<1e-8,'Invalid probability mass')
            group=next(g for g in cfg['groups'] if g['date']==diagnostic['date'] and g['role']=='test')
            values=[float(json.loads((root/(r['market_id']+'-settlement.json')).read_text())['response']['settlement']) for r in group['rules']]
            if all(v in (0.,1.) for v in values) and sum(values)==1:
                y=values.index(1.);scored.append(-math.log(max(probs[y],cfg['probability_floor'])))
        check(len(scored)==len(result['probability_scores']),'Probability scoring denominator mismatch')
        if scored:check(abs(sum(scored)/len(scored)-result['mean_log_loss'])<1e-10,'Probability log loss mismatch')
        summaries.append(dict(strategy=result['strategy'],slippage=result['slippage_per_side'],entries=buys,exits=exits,cash=str(cash),realized=str(realized),open_basis=str(basis),scored_dates=len(scored)))
    audit=dict(status='passed',checks=checks,report_sha256=hashlib.sha256((analysis/'report.json').read_bytes()).hexdigest(),scope='Frozen inputs, disjoint date partitions, source hashes, independent Decimal ledger/fees/settlements, reserve, counts, external expense and probability log loss. Does not validate historical fills or publication availability.',results=summaries)
    output=analysis/'audit.json';check(not output.exists(),'Audit already exists; preserve original evidence');output.write_text(json.dumps(audit,indent=2));print(json.dumps(audit,indent=2))

if __name__=='__main__':main()
