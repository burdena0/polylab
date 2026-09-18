"""Reconcile US ladder scenarios and their incomplete-fill risk independently."""
import sys,json,hashlib,itertools
from pathlib import Path
from decimal import Decimal,ROUND_HALF_EVEN
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT

def require(condition,message):
    if not condition:raise ValueError(message)

def main():
    analysis=Path(sys.argv[1]).resolve();root=analysis.parent;cfg=json.loads((root/'registration.json').read_text());report=json.loads((analysis/'report.json').read_text());history=ROOT/cfg['history_directory'];checks=0
    require(report['registration']==cfg,'Registration mismatch')
    for name,expected in json.loads((root/'code-freeze.json').read_text())['sha256'].items():
        require(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,'Frozen code changed');checks+=1
    for name,expected in report['source_hashes'].items():
        require(hashlib.sha256((history/name).read_bytes()).hexdigest()==expected,'History source changed');checks+=1
    rules={r['slug']:r for g in cfg['groups'] for r in g['rules']};summaries=[]
    for result in report['results']:
        cash=Decimal(cfg['capital']);realized=Decimal(0);fees=Decimal(0);positions={};last=0;dates=set()
        for basket in result['baskets']:
            require(basket['date'] not in dates,'Duplicate basket date');dates.add(basket['date']);q=Decimal(basket['quantity']);legs=basket['legs'];n=len(legs);costs=[]
            require(basket['entry_t']-basket['signal_t']>=cfg['entry_delay_seconds'],'Basket entered early')
            stamps=[leg['quote_t'] for leg in legs];require(min(stamps)>=basket['signal_t']+cfg['entry_delay_seconds'] and max(stamps)-min(stamps)<=cfg['max_leg_skew_seconds'],'Delayed leg refresh/skew failed')
            for leg in legs:
                p=Decimal(leg['price']);cost=p*q+(Decimal('.0695')*p*(1-p)*q).quantize(Decimal('.01'),rounding=ROUND_HALF_EVEN);require(cost==Decimal(leg['cost']),'Leg cost mismatch');costs.append(cost)
            require(sum(costs)==Decimal(basket['cost']) and sum(costs)<=Decimal(cfg['entry_budget']),'Total budget mismatch')
            is_long=result['strategy']=='buy_complete_ladder';floor=q*(1 if is_long else n-1)
            require(floor-sum(costs)==Decimal(basket['net_floor']) and floor==Decimal(basket['terminal_floor']),'Conditional complete-payout floor mismatch')
            losses=[]
            for size in range(1,n):
                for indexes in itertools.combinations(range(n),size):
                    # A missing winning leg makes the long subset pay zero.
                    # A short subset pays size-1 contracts when one selected leg wins.
                    subset_floor=Decimal(0) if is_long else q*(size-1)
                    losses.append(subset_floor-sum(costs[i] for i in indexes))
            require(min([Decimal(0)]+losses)==Decimal(basket['partial_fill_worst_pnl']),'Partial-fill risk mismatch');checks+=1
        for trade in result['ledger']:
            require(trade['t']>=last,'Nonchronological ledger');last=trade['t'];slug=trade['slug'];q=Decimal(trade['quantity']);p=Decimal(trade['price']);fee=Decimal(trade['fee']);require(slug in rules and q>0 and q==int(q),'Invalid instrument/quantity')
            if trade['kind']=='buy':
                require(slug not in positions,'Duplicate holding');cost=p*q+fee;cash-=cost;fees+=fee;positions[slug]=(q,cost);require(trade['side']==result['strategy'],'Incorrect basket side')
            else:
                require(trade['kind']=='settlement' and slug in positions,'Invalid close');oldq,basis=positions.pop(slug);require(oldq==q and fee==0,'Settlement quantity/fee mismatch');raw=json.loads((history/(rules[slug]['market_id']+'-settlement.json')).read_text())['response'];value=Decimal(str(raw['settlement']));value=value if result['strategy']=='buy_complete_ladder' else 1-value;require(raw['slug']==slug and value==p,'Settlement value mismatch');gain=p*q-basis;require(gain==Decimal(trade['pnl']),'Trade P&L mismatch');cash+=p*q;realized+=gain
            require(cash>=Decimal(cfg['reserve']) and cash==Decimal(trade['cash']),'Reserve/cash mismatch');checks+=1
        basis=sum((v[1] for v in positions.values()),Decimal(0))
        require(cash==Decimal(result['cash']) and realized==Decimal(result['realized_pnl']) and basis==Decimal(result['open_basis']) and fees==Decimal(result['fees']),'Summary mismatch')
        require(cash+basis==Decimal(cfg['capital'])+realized,'Accounting conservation failed')
        expense=cfg['monthly_subscription']*(report['period_end']-report['period_start'])/(30*86400);require(abs(float(realized)-expense-result['realized_after_subscription'])<1e-9,'Expense mismatch')
        summaries.append(dict(strategy=result['strategy'],slippage=result['slippage_per_side'],basket_scenarios=len(dates),realized_pnl=str(realized),cash=str(cash),open_basis=str(basis)))
    audit=dict(status='passed',checks=checks,report_sha256=hashlib.sha256((analysis/'report.json').read_bytes()).hexdigest(),scope='Frozen code, receipts, accounting, quote timing, conditional payout floors and partial-fill worst losses. Historical fills and data semantics remain unverified.',results=summaries)
    path=analysis/'audit.json';require(not path.exists(),'Preserve existing audit');path.write_text(json.dumps(audit,indent=2));print(json.dumps(audit,indent=2))

if __name__=='__main__':main()
