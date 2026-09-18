"""Task-specific model speed/schema benchmark; does not measure trading alpha."""
import json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.agent import review,MODEL
from polylab.research import ROOT
rows=[]
cases=[dict(id='thin',probability_up=.54,up_ask=.60,down_ask=.55,spread=.12,up_depth=1,down_depth=1,momentum=-.03,volatility=.04,imbalance=-.6,quote_freshness='unknown'),dict(id='positive',probability_up=.80,up_ask=.52,down_ask=.50,spread=.02,up_depth=300,down_depth=300,momentum=.02,volatility=.005,imbalance=.4,quote_freshness='unknown')]
for i in range(3):
    result,stats=review(cases)
    rows.append(dict(decisions=result,**stats))
    print(json.dumps(rows[-1]),flush=True)
(ROOT/'data'/'model-benchmark.json').write_text(json.dumps(dict(model=MODEL,trials=rows,scope='Timing, schema compliance, and simple risk-reasoning cases; not a profitability benchmark'),indent=2))
