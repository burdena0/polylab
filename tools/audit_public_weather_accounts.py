"""Bounded, read-only international leaderboard evidence; no trading client."""
import hashlib,json,re,sys,time,statistics
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]

def save(path,value):
    path.write_text(json.dumps(value,indent=2),encoding='utf-8')

def main():
    root=ROOT/'data/public-weather-accounts'/str(time.time_ns());root.mkdir(parents=True)
    save(root/'registration.json',dict(created_at=time.time(),selection='Top 3 all-time and top 3 monthly WEATHER accounts ranked by official PNL; union by wallet.',scope='International public-data benchmark only. US strategy transfer unproven.',max_requests=20,closed_sample='Latest 50 by timestamp, not sorted by profit',activity_sample='Latest 200 trades',live_execution=False))
    session=requests.Session();session.trust_env=False
    def get(name,path,params):
        if path not in ['/v1/leaderboard','/closed-positions','/activity']:raise ValueError('Unapproved path')
        start=time.time()
        with session.get('https://data-api.polymarket.com'+path,params=params,headers={'User-Agent':'PolyLab public strategy research'},timeout=(5,15),allow_redirects=False,stream=True) as r:
            if r.status_code!=200:raise ValueError('HTTP '+str(r.status_code))
            raw=b''
            for chunk in r.iter_content(65536):
                raw+=chunk
                if len(raw)>4_000_000:raise ValueError('Response cap')
            result=json.loads(raw)
            if not isinstance(result,list):raise ValueError('Expected list')
            save(root/(name+'.json'),dict(receipt=dict(url=r.url,requested_at=start,received_at=time.time(),sha256=hashlib.sha256(raw).hexdigest()),raw_text=raw.decode(),response=result))
        time.sleep(1)
        return result
    boards={};chosen={};errors=[]
    for period in ['ALL','MONTH']:
        rows=get('leaderboard-'+period,'/v1/leaderboard',dict(category='WEATHER',timePeriod=period,orderBy='PNL',limit=20,offset=0));boards[period]=rows
        for row in rows[:3]:chosen.setdefault(row['proxyWallet'],row)
    summaries=[]
    for wallet,profile in chosen.items():
        if not re.fullmatch(r'0x[0-9a-fA-F]{40}',wallet):raise ValueError('Wallet format')
        try:
            closed=get(wallet+'-closed','/closed-positions',dict(user=wallet,limit=50,offset=0,sortBy='TIMESTAMP',sortDirection='DESC'))
            trades=get(wallet+'-trades','/activity',dict(user=wallet,type='TRADE',limit=200,offset=0,sortBy='TIMESTAMP',sortDirection='DESC'))
            if any(r.get('proxyWallet','').lower()!=wallet.lower() for r in closed+trades):raise ValueError('Wallet identity mismatch')
            weather=[r for r in closed if 'temperature' in r.get('title','').lower()]
            wt=[r for r in trades if 'temperature' in r.get('title','').lower()]
            buys=[r for r in wt if r.get('side')=='BUY'];ts=sorted(set(r['timestamp'] for r in wt))
            pnl=[float(r['realizedPnl']) for r in weather]
            cost=sum(float(r['totalBought'])*float(r['avgPrice']) for r in weather)
            city={}
            for r in weather:
                match=re.search(r'temperature in (.+?) on ',r.get('title',''),re.I)
                label=match.group(1) if match else 'unparsed';city[label]=city.get(label,0)+float(r['realizedPnl'])
            summaries.append(dict(user=profile['userName'],wallet=wallet,profile_url='https://polymarket.com/profile/'+wallet,
                leaderboard={p:next((dict(rank=r['rank'],pnl=r['pnl'],volume=r['vol']) for r in rows if r['proxyWallet']==wallet),None) for p,rows in boards.items()},
                closed_rows=len(closed),temperature_closed_rows=len(weather),sample_realized_pnl=sum(pnl),sample_cost_proxy=cost,
                sample_worst_position=min(pnl,default=None),sample_best_position=max(pnl,default=None),cities=city,
                trade_rows=len(trades),temperature_trade_rows=len(wt),temperature_buy_rows=len(buys),
                buy_price_median=statistics.median(float(r['price']) for r in buys) if buys else None,
                buy_at_or_above_90c=sum(float(r['price'])>=.90 for r in buys),
                median_distinct_trade_gap_seconds=statistics.median(b-a for a,b in zip(ts,ts[1:])) if len(ts)>1 else None,
                first_trade_in_sample=min(ts,default=None),last_trade_in_sample=max(ts,default=None),bot_status='Unverified',bankroll_roi=None,
                caveats=['Bounded recent samples, not lifetime reconciliation.','Closed-position PNL and leaderboard PNL have different scopes.','Cost proxy is turnover basis, not concurrent capital or deposits.','Trade cadence can reflect fragmented fills, not necessarily automated decisions.','A 90c entry does not establish proximity to settlement.']))
        except Exception as exc:errors.append(dict(wallet=wallet,error=str(exc)))
    report=dict(created_at=time.time(),accounts=summaries,errors=errors,source='Official international Polymarket data API',us_execution_eligible=False,polylab_profit=None)
    save(root/'report.json',report);save(ROOT/'data/public-weather-accounts-latest.json',dict(directory=str(root)))
    print(json.dumps(dict(directory=str(root),accounts=summaries,errors=errors)),flush=True)

if __name__=='__main__':main()
