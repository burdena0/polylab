# US agent comparison

Saved experiment: `data/us-agent/1789688903639544700`. This is an exploratory ablation on the existing 24-market feasibility sample, after its baseline results were already inspected. It is not untouched validation.

Qwen3.5:9b received four anonymous numerical packets, including only observations available by the signal time, bid/ask, selected side, price movement and explicit absence of calibrated probabilities or depth. No market names, dates, future prices or outcomes were passed. Exact packets, prompt hash, model, mapping, decisions and request measurements are preserved. The agent could only veto an existing signal.

| Rule | No agent | Spread filter | Agent | Agent + measured delay |
| --- | ---: | ---: | ---: | ---: |
| Momentum | -$9.69 (3 trades) | $0 (0 trades) | -$4.11 (1 trade) | -$4.11 (1 trade) |
| Mean reversion | -$4.11 (1 trade) | $0 (0 trades) | -$4.11 (1 trade) | -$4.11 (1 trade) |

Figures are realized price-scenario trading P&L before subscription expense; all positions closed. Historical display quotes do not establish depth or actual fills. The deterministic comparison allowed only signal spreads at most three cents and selected-side prices between .15 and .85; it vetoed every entry. Zero trades are not profitability.

The request took 9.91 seconds, including 6.96 seconds model loading and 1.82 seconds generation. The delayed arm adds the full measured request wall time, rounded up to 10 seconds, to the existing 60-second delay for each decision. It preserves the original signal and side rather than reusing approval on a later signal. Sparse historical observations limit sensitivity to small latency changes.

The agent reduced exposure and one baseline loss, but still lost money. Four decisions on selected related contracts cannot establish a general advantage. The existing forward-paper experiment therefore remains deterministic and unchanged. A future agent comparison requires a registered untouched US opportunity set, independent predictive inputs and enough completed observations.

Reproduce with `.venv\Scripts\python.exe tools/compare_us_agent.py data/us-history/1789687853207852500`; every run creates a separate directory and uses only the already installed local model. No model purchase, cloud API charge or exchange order is involved.
