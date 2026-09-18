"""Register the capital-constrained combined test before transfer P&L inspection."""
import hashlib, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT

source = Path(sys.argv[1]).resolve()
if list(source.glob('analysis-*')):
    raise ValueError('This registration requires transfer P&L still uncomputed')
cfg = json.loads((source/'registration.json').read_text())
dest = ROOT/'data/us-portfolio'/str(time.time_ns())
dest.mkdir(parents=True)
registration = dict(created_at=time.time(), source_transfer=str(source.relative_to(ROOT)),
                    source_registration_sha256=hashlib.sha256((source/'registration.json').read_bytes()).hexdigest(),
                    strategies=cfg['strategies'], slippage_per_side=cfg['slippage_per_side'],
                    capital='50', reserve='40', entry_budget='5', monthly_subscription=200,
                    selection='All four registered transfer stations and all nine dates. One candidate per station-date uses the original signal, 60-second delayed quote, fee and expected-dollar rules.',
                    allocation='Each arm shares one $50 cash account across all stations, preserving $40 reserve and $5 maximum entry. Process timestamped entries chronologically; settlements first at equal timestamps. Simultaneous entries use descending estimated dollar edge, then slug. Never borrow or anticipate later settlements or quotes.',
                    design='Eight independent comparison scenarios (four strategies, two costs). Do not add their profits or initial capital. No coefficients refitted.',
                    preregistration_limit='Registered while transfer downloads were in progress, before transfer profitability was computed. NYC pilot results and earlier station weather-error summaries were already known.',
                    live_execution=False)
(dest/'registration.json').write_text(json.dumps(registration, indent=2))
print(json.dumps(dict(directory=str(dest), registration=registration), indent=2))
