"""Independent cash/fee/receipt/optimizer audit of common-time simulations."""
import json, sys, hashlib, math
from pathlib import Path
from decimal import Decimal as D, ROUND_HALF_EVEN, ROUND_CEILING
from urllib.parse import urlparse, parse_qs
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    dest=Path(sys.argv[1]).resolve();root=dest.parent;project=Path(__file__).resolve().parents[1]
    report=json.loads((dest/'report.json').read_text());cfg=json.loads((root/'registration.json').read_text());checks=0
    def check(condition,message):
        nonlocal checks
        checks+=1
        if not condition: raise AssertionError(message)
    check(report['registration']==cfg,'Registration')
    check(cfg['monthly_subscription']==0 and not cfg['live_execution'],'Cost/execution policy')
    for name,sha in json.loads((root/'code-freeze.json').read_text())['sha256'].items():check(digest(project/name)==sha,'Code/input freeze '+name)
    model=json.loads((project/cfg['source_model']).read_text())['combination']
    check(cfg['beta']==model['beta'] and cfg['model_asof']==model['asof'],'Original frozen probability coefficients')
    for name,reuse in json.loads((root/'reused-sources.json').read_text()).items():
        check(digest(root/name)==reuse['sha256']==digest(project/reuse['source']),'Reused receipt provenance')
    groups={};raw_prices={};payouts={};releases={}
    climate_rows=json.loads((project/cfg['forecast_rows']).read_text())['rows']
    climate_rows={(r['station'],r['date']):r for r in climate_rows}
    for g in cfg['groups']:
        groups[g['target'],g['station']]=g
        release=(datetime.fromisoformat(g['date'])+timedelta(days=1)).replace(hour=11,tzinfo=ZoneInfo('America/New_York')).timestamp()
        if (g['station'],g['date']) in climate_rows:release=max(release,climate_rows[g['station'],g['date']]['observation_issued_at'])
        for r in g['rules']:
            releases[r['slug']]=release
            for kind in ['history','settlement']:
                path=root/(r['market_id']+'-'+kind+'.json');doc=json.loads(path.read_text());url=urlparse(doc['receipt']['url'])
                check(digest(path)==report['source_hashes'][path.name],'Receipt hash')
                check(url.scheme=='https' and url.hostname=='gateway.polymarket.us','US venue')
                if kind=='settlement':
                    check(doc['response']['slug']==r['slug'],'Payout identity');payouts[r['slug']]=D(doc['response']['settlement'])
                else:
                    check(parse_qs(url.query).get('symbol')==[r['slug']],'Price identity')
                    # Independent parse of original API response (not normalized scenario output).
                    raw_prices[r['slug']]=doc['response']
    def charge(p,q): return (D('.0695')*q*p*(1-p)).quantize(D('.01'),rounding=ROUND_HALF_EVEN)
    # Normalize with public documented representation, after validating all original receipts above.
    sys.path.insert(0,str(project))
    from polylab.us_replay import normalize_history
    history={slug:normalize_history(raw,-10**12,10**12)[0] for slug,raw in raw_prices.items()}
    def options(g,slip):
        qs=[]
        for r in g['rules']:
            older=[p for p in history[r['slug']] if p['t']<=g['target']]
            if not older or g['target']-older[-1]['t']>cfg['max_quote_age_seconds']:return []
            qs.append(older[-1])
        weights=[max(p['mid'],1e-6)**cfg['beta'] for p in qs];total=sum(weights);out=[]
        for rule,quote,w in zip(g['rules'],qs,weights):
            for side,prob,raw in [('long',w/total,D(str(quote['ask']))),('short',1-w/total,1-D(str(quote['bid'])))]:
                p=raw+D(slip)
                if not 0<p<1:continue
                for q in range(1,int(D(cfg['entry_budget'])/p)+1):
                    cost=p*q+charge(p,q);ev=D(str(prob))*q-cost
                    if cost>D(cfg['entry_budget']):break
                    if ev>=D(cfg['min_expected_dollars']):out.append(dict(slug=rule['slug'],side=side,quantity=q,probability=prob,cost_cents=int((cost*100).to_integral_value(rounding=ROUND_CEILING)),expected=ev))
        return out
    for result in report['results']:
        cash=D(cfg['capital']);realized=D(0);fees=D(0);positions={};selected={};last=-math.inf
        # Decision cash must use only completed ledger events at that time.
        for dec in result['decisions']:
            prior=[l for l in result['ledger'] if l['t']<=dec['t']]
            available=(D(prior[-1]['cash']) if prior else D(cfg['capital']))-D(cfg['reserve'])
            check(available==D(dec['available']),'No future cash')
            opts={station:options(g,result['slippage_per_side']) for (t,station),g in groups.items() if t==dec['t']}
            eligible=[city for city,v in opts.items() if v];check(len(eligible)==dec['eligible_cities'],'Eligible cities')
            check(len({o['station'] for o in dec['selected']})==len(dec['selected']),'One position per city')
            budget=int(available*100);check(sum(o['cost_cents'] for o in dec['selected'])<=budget,'Decision budget')
            achieved=D(0)
            for o in dec['selected']:
                matched=[v for v in opts[o['station']] if (v['slug'],v['side'],v['quantity'])==(o['slug'],o['side'],o['quantity'])]
                check(len(matched)==1,'Selected option available at signal');v=matched[0]
                check(abs(v['expected']-D(o['expected']))<D('1e-10') and v['cost_cents']==o['cost_cents'],'Signal expected dollars')
                achieved+=v['expected'];selected[o['slug']]=o
            if result['strategy']=='expected_dollars' and eligible:
                flattened=[(c,o) for c in eligible for o in opts[c]]
                costs=np.array([o['cost_cents'] for c,o in flattened],dtype=float)
                rows=[costs]+[np.array([int(c==city) for c,o in flattened],dtype=float) for city in eligible]
                fit=milp(c=-np.array([float(o['expected']) for c,o in flattened]),integrality=np.ones(len(flattened)),bounds=Bounds(0,1),constraints=LinearConstraint(np.array(rows),np.zeros(len(rows)),np.array([budget]+[1]*len(eligible))),options={'time_limit':10,'mip_rel_gap':0})
                check(fit.success and abs(float(achieved)+fit.fun)<1e-7,'Independent integer optimizer agrees')
            elif result['strategy']=='equal_budget' and eligible:
                cap=min(500,budget//len(eligible));expected=sum((max((o['expected'] for o in opts[c] if o['cost_cents']<=cap),default=D(0)) for c in eligible),D(0))
                check(abs(achieved-expected)<D('1e-10'),'Equal allocation optimum within each city budget')
        for l in result['ledger']:
            check(l['t']>=last,'Chronological ledger');last=l['t'];p=D(l['price']);q=D(l['quantity']);slug=l['slug']
            if l['kind']=='buy':
                o=selected[slug];check(q==int(q) and 0<q<=o['quantity'],'Frozen whole quantity')
                points=[p for p in history[slug] if p['t']>=o['signal_t']+cfg['entry_delay_seconds']]
                check(bool(points) and l['t']==points[0]['t'] and l['t']-o['signal_t']-cfg['entry_delay_seconds']<=cfg['max_quote_age_seconds'],'First delayed quote')
                qp=points[0];expected_price=(D(str(qp['ask'])) if o['side']=='long' else 1-D(str(qp['bid'])))+D(result['slippage_per_side'])
                check(p==expected_price,'Delayed source price')
                f=charge(p,q);basis=p*q+f;check(f==D(l['fee']),'Rounded fee')
                check(basis<=min(D(o['cost_cents'])/100,D(cfg['entry_budget'])),'Reserved signal budget')
                check(D(str(o['probability']))*q-basis>=D(cfg['min_expected_dollars']),'Delayed net expected edge')
                cash-=basis;fees+=f;positions[slug]=(q,basis)
            else:
                oq,basis=positions.pop(slug);o=selected[slug];expected=payouts[slug] if o['side']=='long' else 1-payouts[slug]
                check(l['t']==releases[slug],'Registered settlement release assumption')
                check(p==expected and oq==q and D(l['fee'])==0,'Source settlement')
                pnl=p*q-basis;check(pnl==D(l['pnl']),'Settlement P&L');realized+=pnl;cash+=p*q
            check(cash==D(l['cash']) and cash>=D(cfg['reserve']),'Shared account/reserve')
        check(cash==D(result['cash']) and realized==D(result['realized_pnl']) and fees==D(result['fees']),'Final P&L')
        check(sum((v[1] for v in positions.values()),D(0))==D(result['open_basis']),'Open basis')
        check(cash+D(result['open_basis'])==D(cfg['capital'])+realized,'Account identity')
    out=dict(status='passed',checks=checks,report_sha256=digest(dest/'report.json'),audit_code_sha256=digest(Path(__file__)),note='Independent Decimal ledger and raw receipt checks; independent MILP verifies each optimal allocation. Historical depth/fills and release availability remain unverified.')
    (dest/'audit.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

if __name__=='__main__':main()
