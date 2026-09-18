"""Loopback-only PolyLab dashboard API. This application contains no order client."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from pathlib import Path
import csv,io,json,mimetypes,threading,os
from .research import ROOT,run,IMPLEMENTED
from .probability import odds_to_probabilities
from .paper import PaperTrader
from .weather import WeatherArchive
from .coherence import STRATEGIES as COHERENCE, evaluate as evaluate_coherence, example as coherence_example
from .coherence_replay import run as run_coherence, latest as latest_coherence
from .risk import STRATEGIES as RISK, evaluate as evaluate_risk, example as risk_example
from .risk_replay import run as run_risk, latest as latest_risk
from .paper_cohort import PaperCohort
from .public_inputs import WeatherInputs
from .oracle import OracleArchive
from .weather_probability import STRATEGIES as WEATHER_MODELS, distribution as weather_distribution, fit_bias as weather_bias
from .weather_model_run import run as run_weather_models, latest as latest_weather_models
from .us_marketdata import USCollector
from .us_paper import USPaper
from .us_scope import US_ONLY,restrict_catalog
PORT=8788
paper=PaperTrader();guide=PaperTrader('guide-btc-momentum',900);weather=WeatherArchive();run_lock=threading.Lock()
cohort=PaperCohort()
inputs=WeatherInputs(weather.probability_quotes);oracle=OracleArchive()
us=USCollector()
us_paper=USPaper()
def paper_state():return dict(**paper.snapshot(),other_accounts=[guide.snapshot()]+cohort.snapshots())
def start_paper():
    if US_ONLY:raise ValueError('International paper workers are archived. US paper adapters are being implemented.')
    paper.start();guide.start();cohort.start();return paper_state()
def stop_paper():paper.stop();guide.stop();cohort.stop();return paper_state()
def start_weather():
    if US_ONLY:raise ValueError('International weather/Chainlink collectors are archived. Use Polymarket US data.')
    weather.start();inputs.start();oracle.start();return weather.snapshot()
def stop_weather():weather.stop();inputs.stop();oracle.stop();return weather.snapshot()

def latest():
    path=ROOT/'data'/'latest.json'
    if not path.exists():return run()
    rid=json.loads(path.read_text())['id']
    return json.loads((ROOT/'data'/'runs'/rid/'report.json').read_text())

def agent_result():
    for name in ['agent-comparison-momentum.json','agent-comparison.json']:
        p=ROOT/'data'/name
        if p.exists():return json.loads(p.read_text())
    return {'status':'pending','decisions':{}}

def catalog():
    rows=json.loads((ROOT/'data'/'catalog.json').read_text())
    for row in rows:
        row['status']='Backtest adapter' if row['id'] in IMPLEMENTED else 'Research specification'
        if row['status']=='Research specification':row['note']='Not implemented. Requires the listed data and a strategy-specific model; this catalogue entry is not an executable strategy.'
        elif row['id']=='yes-no-complement-arbitrage':row['note']='Idealized collateralized split-and-sell scan. Atomic legs and on-chain costs unavailable; no executable arbitrage claim.'
        elif row['id'] in ['mean-reversion-on-volatile-markets','order-flow-imbalance-microstructure-model']:row['note']='Research approximation using sampled top-of-book only. Missing event/news context or complete event flow can change the result.'
        else:row['note']='Implemented research rule with explicit local parameters. Not a claim of exact reproduction or profitability.'
        if row['id'] in COHERENCE:
            row['evaluator']='coherence'
            row['status']='Basket replay + evaluator' if COHERENCE[row['id']][0]=='binary' else 'Basket evaluator'
            row['note']='Executable cost/depth-aware basket evaluator. Explicit settlement relationships required. Terminal payout floors are conditional mathematical bounds, not realized profit. Binary variants also have delayed historical replay; no chain transactions are sent.'
        if row['id'] in RISK:
            row['evaluator']='risk';row['status']='Risk module'
            row['note']='Executable portfolio control, not an independent alpha signal. API accepts explicit probability, covariance, scenario or depth inputs. Matched risk-overlay and unused-market studies are saved separately; current results do not establish profitable deployment.'
        if row['id'] in WEATHER_MODELS:
            row['evaluator']='weather_probability';row['status']='Temperature ensemble component'
            row['note']='Full GFS/ECMWF/ICON member capture, exact-band probability counts, station bias/spread fitting, observed-extreme conditioning and costed quote scans. Current station calibration and settlement timezone/rounding verification are incomplete. Temperature subset only; hurricane/snowfall cases and historical forecast-profit replay remain unimplemented.'
    existing={r['id'] for r in rows}
    for sid,name in IMPLEMENTED.items():
        if sid in existing or sid=='cash':continue
        row=dict(id=sid,name=name,category='Paper methods',description=name,requirements=['Timestamped input probabilities or price features','Separate training, calibration, and evaluation periods'],status='Backtest adapter',url='https://www.polyresearchrobotics.com/guide/how-to-build-a-polymarket-trading-bot')
        if sid=='avellaneda-stoikov':row.update(status='Quote formula only',note='Quote generator implemented. Passive fills are not backtested without trade events and queue evidence.',url='https://math.nyu.edu/inmemoriam/avellaneda/HighFrequencyTrading.pdf')
        if sid=='guide-btc-momentum':row.update(status='Forward paper only',note='Live 15-minute paper signal uses the guide’s public Coinbase fallback. Historical oracle data is unavailable; the 5-minute book archive cannot reproduce this signal.')
        if sid=='shin':row.update(description='Shin Eq. 3 solved for bookmaker insider fraction with a normalized probability vector.',url='https://doi.org/10.1016/j.ijforecast.2014.02.008')
        if sid=='benter':row.update(description='Fit alpha and beta to held-out model probabilities and public probabilities, using multinomial log likelihood. Book features replace horse fundamentals in this adaptation.')
        rows.append(row)
    return restrict_catalog(rows) if US_ONLY else rows

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,value,status=200):
        body=json.dumps(value,allow_nan=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def host_ok(self):return self.headers.get('Host') in (f'127.0.0.1:{PORT}',f'localhost:{PORT}')
    def do_GET(self):
        if not self.host_ok():return self.respond({'error':'Loopback host required'},403)
        p=urlparse(self.path);query=parse_qs(p.query)
        try:
            if p.path=='/api/report':return self.respond(latest())
            if p.path=='/api/catalog':return self.respond(catalog())
            if p.path=='/api/us':return self.respond(us.snapshot())
            if p.path=='/api/us/paper':return self.respond(us_paper.snapshot())
            if p.path in ['/api/us/transfer','/api/us/transfer/chart','/api/us/portfolio','/api/us/portfolio/chart']:
                import hashlib
                family='us-transfer' if '/transfer' in p.path else 'us-portfolio'
                pointer=ROOT/('data/'+family+'-latest.json')
                if not pointer.exists():return self.respond({'status':'pending'})
                directory=Path(json.loads(pointer.read_text())['directory']).resolve()
                if not directory.is_relative_to((ROOT/'data'/family).resolve()):raise ValueError('Invalid US validation study path')
                if not (directory/'audit.json').exists():return self.respond({'status':'pending_audit'})
                raw=(directory/'report.json').read_bytes();audit=json.loads((directory/'audit.json').read_text())
                if audit.get('status')!='passed' or audit.get('report_sha256')!=hashlib.sha256(raw).hexdigest():raise ValueError('US validation audit mismatch')
                if p.path.endswith('/chart'):
                    filename='portfolio-profit.png' if family=='us-portfolio' else ('transfer-slippage.png' if query.get('slippage',['0'])[0]=='.005' else 'transfer-profit.png')
                    return self.send_file(directory/filename)
                return self.respond(json.loads(raw))
            if p.path in ['/api/us/baskets','/api/us/baskets/chart']:
                pointer=ROOT/'data/us-baskets-latest.json'
                if not pointer.exists():return self.respond({'status':'pending'},404)
                directory=Path(json.loads(pointer.read_text())['directory']).resolve()
                if not directory.is_relative_to((ROOT/'data/us-baskets').resolve()):raise ValueError('Invalid US basket study path')
                if p.path.endswith('/chart'):return self.send_file(directory/'basket-profit.png')
                return self.respond(json.loads((directory/'report.json').read_text()))
            if p.path in ['/api/us/benter','/api/us/benter/chart']:
                pointer=ROOT/'data/us-benter-latest.json'
                if not pointer.exists():return self.respond({'status':'pending'},404)
                directory=Path(json.loads(pointer.read_text())['directory']).resolve()
                if not directory.is_relative_to((ROOT/'data/us-benter').resolve()):raise ValueError('Invalid US combination study path')
                if p.path.endswith('/chart'):return self.send_file(directory/'benter-profit.png')
                return self.respond(json.loads((directory/'report.json').read_text()))
            if p.path in ['/api/us/weather','/api/us/agent']:
                family='us-weather' if p.path.endswith('/weather') else 'us-agent'
                pointer=ROOT/'data/us-weather/latest.json' if family=='us-weather' else ROOT/'data/us-agent-latest.json'
                if not pointer.exists():return self.respond({'status':'pending'},404)
                directory=Path(json.loads(pointer.read_text())['directory']).resolve()
                if not directory.is_relative_to((ROOT/'data'/family).resolve()):raise ValueError('Invalid US research report path')
                return self.respond(json.loads((directory/'report.json').read_text()))
            if p.path in ['/api/us/weather/replay','/api/us/weather/replay/chart']:
                pointer=ROOT/'data/us-weather-replay-latest.json'
                if not pointer.exists():return self.respond({'status':'pending'},404)
                directory=Path(json.loads(pointer.read_text())['directory']).resolve()
                if not directory.is_relative_to((ROOT/'data/us-weather-history').resolve()):raise ValueError('Invalid US weather study path')
                if p.path.endswith('/chart'):return self.send_file(directory/'weather-profit.png')
                return self.respond(json.loads((directory/'report.json').read_text()))
            if p.path in ['/api/us/replay','/api/us/replay/chart']:
                pointer=ROOT/'data/us-replay-latest.json'
                if not pointer.exists():return self.respond({'status':'pending'},404)
                directory=Path(json.loads(pointer.read_text())['directory']).resolve()
                if not directory.is_relative_to((ROOT/'data/us-history').resolve()):raise ValueError('Invalid US report path')
                if p.path.endswith('/chart'):return self.send_file(directory/'realized-pnl.png')
                return self.respond(json.loads((directory/'report.json').read_text()))
            if p.path=='/api/paper':return self.respond(paper_state())
            if p.path=='/api/weather':return self.respond(weather.snapshot())
            if p.path=='/api/public-inputs':return self.respond(dict(weather=inputs.snapshot(),oracle=oracle.snapshot()))
            if p.path=='/api/weather/models':return self.respond(latest_weather_models())
            if p.path=='/api/agent':return self.respond(agent_result())
            if p.path=='/api/coherence/example':return self.respond(coherence_example(query.get('strategy',[''])[0]))
            if p.path=='/api/coherence/report':return self.respond(latest_coherence())
            if p.path=='/api/coherence/live':return self.respond(weather.coherence_pair())
            if p.path=='/api/risk/example':return self.respond(risk_example(query.get('strategy',[''])[0]))
            if p.path=='/api/risk/report':return self.respond(latest_risk())
            if p.path=='/api/profit/report':
                root=ROOT/'data/profit-study-v1';pointer=json.loads((root/'latest.json').read_text());return self.respond(json.loads((root/'runs'/pointer['run']/'report.json').read_text()))
            if p.path=='/api/weather/replay':return self.respond(weather.replay(query.get('file',[''])[0],max(0,min(100000,int(query.get('offset',['0'])[0])))))
            if p.path=='/api/weather/download':
                name=query.get('file',[''])[0]
                if name not in weather.state['files'] or Path(name).name!=name:raise ValueError('Unknown archive')
                # Manifest size is updated only after a complete gzip member is closed.
                return self.send_file(weather.root/name,attachment=name,length=weather.state['files'][name]['bytes'])
            if p.path=='/api/export':
                result=latest()['results'][query.get('strategy',['benter'])[0]];fields=['condition','side','entry_time','exit_time','quantity','cost','proceeds','pnl']
                buffer=io.StringIO();w=csv.DictWriter(buffer,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(result['ledger']);body=buffer.getvalue().encode()
                self.send_response(200);self.send_header('Content-Type','text/csv');self.send_header('Content-Disposition','attachment; filename="polylab-trades.csv"');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
            if p.path.startswith('/api/'):return self.respond({'error':'Not found'},404)
            static=(ROOT/'web'/'dist').resolve();target=(static/p.path.lstrip('/')).resolve()
            if not target.is_relative_to(static):return self.respond({'error':'Invalid path'},403)
            if not target.is_file():target=static/'index.html'
            return self.send_file(target)
        except (ValueError,KeyError) as exc:self.respond({'error':str(exc)},400)
        except Exception as exc:self.respond({'error':type(exc).__name__},500)
    def send_file(self,path,attachment=None,length=None):
        size=path.stat().st_size if length is None else length;self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(path))[0] or 'application/octet-stream');self.send_header('Content-Length',str(size));self.send_header('X-Content-Type-Options','nosniff')
        if attachment:self.send_header('Content-Disposition',f'attachment; filename="{attachment}"')
        self.end_headers()
        with path.open('rb') as f:
            remaining=size
            while remaining:
                chunk=f.read(min(65536,remaining))
                if not chunk:break
                self.wfile.write(chunk);remaining-=len(chunk)
    def do_POST(self):
        origin=self.headers.get('Origin')
        if not self.host_ok() or (origin and origin not in (f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}')):return self.respond({'error':'Same-origin request required'},403)
        if self.headers.get('Content-Type')!='application/json':return self.respond({'error':'JSON required'},415)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<65536:raise ValueError('Invalid request size')
            body=json.loads(self.rfile.read(size))
            if self.path=='/api/us/paper/start':return self.respond(us_paper.start())
            if self.path=='/api/us/paper/stop':us_paper.stop();return self.respond(us_paper.snapshot())
            if US_ONLY and self.path in ['/api/backtest','/api/coherence/backtest','/api/risk/backtest','/api/weather/backtest','/api/weather/models/run']:
                return self.respond({'error':'International experiments are archived under US-only scope. US validation is pending.'},409)
            if self.path=='/api/backtest':
                if not run_lock.acquire(blocking=False):return self.respond({'error':'A backtest is already running'},409)
                try:return self.respond(run(config=body,agent=agent_result()))
                finally:run_lock.release()
            if self.path=='/api/odds':return self.respond({m:odds_to_probabilities(body['odds'],m) for m in ['normalization','shin']})
            if self.path=='/api/coherence/evaluate':return self.respond(evaluate_coherence(body['strategy'],body['document'],body.get('costs')))
            if self.path=='/api/risk/evaluate':return self.respond(evaluate_risk(body['strategy'],body['document']))
            if self.path=='/api/risk/backtest':
                if not run_lock.acquire(blocking=False):return self.respond({'error':'A backtest is already running'},409)
                try:return self.respond(run_risk(body))
                finally:run_lock.release()
            if self.path=='/api/coherence/backtest':
                if not run_lock.acquire(blocking=False):return self.respond({'error':'A backtest is already running'},409)
                try:return self.respond(run_coherence(body))
                finally:run_lock.release()
            if self.path=='/api/paper/start':return self.respond(start_paper())
            if self.path=='/api/paper/stop':return self.respond(stop_paper())
            if self.path=='/api/weather/start':return self.respond(start_weather())
            if self.path=='/api/weather/stop':return self.respond(stop_weather())
            if self.path=='/api/weather/backtest':return self.respond(weather.backtest(body['file']))
            if self.path=='/api/weather/models/run':
                if not run_lock.acquire(blocking=False):return self.respond({'error':'A research run is already active'},409)
                try:return self.respond(run_weather_models(weather.probability_quotes()))
                finally:run_lock.release()
            if self.path=='/api/weather/probability':return self.respond(weather_distribution(body['members'],body['rule'],body['bands'],body.get('bias'),body.get('model'),body['asof'],body.get('observed')))
            if self.path=='/api/weather/bias-fit':return self.respond(weather_bias(body['rows'],body['station'],body['metric'],body['model'],body['asof']))
            self.respond({'error':'Not found'},404)
        except (ValueError,KeyError,TypeError) as exc:self.respond({'error':str(exc)},400)
        except Exception as exc:self.respond({'error':type(exc).__name__},500)

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--paper',action='store_true');parser.add_argument('--weather',action='store_true');args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    if US_ONLY:us.start();us_paper.start()
    else:
        if args.paper:start_paper()
        if args.weather:start_weather()
    (ROOT/'data'/'server-pid.json').write_text(json.dumps({'pid':os.getpid(),'port':PORT}))
    print(f'PolyLab listening at http://127.0.0.1:{PORT}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:us.stop();us_paper.stop();stop_paper();stop_weather();server.server_close()
if __name__=='__main__':main()
