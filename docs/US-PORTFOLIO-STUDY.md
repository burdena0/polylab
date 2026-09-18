> Cost correction (September 17): No paid model/data subscription is configured for PolyLab. The inherited $200/month is a legacy hypothetical sensitivity, not an actual bill. Current profit excludes this deduction; fees and slippage remain. Frozen historical artifacts retain their original assumptions for reproducibility.

# US shared-capital profit test

Registration `data/us-portfolio/1789693764400920100/registration.json` was saved while the four-city transfer downloads were still in progress and before transfer profitability was computed. It uses all 36 station-dates from `data/us-transfer/1789692627926092500`, with the same frozen New York coefficients, four strategies and two slippage cases. It is a new allocation comparison, not a change to earlier experiments. New York results and earlier station weather-error summaries were already known.

Each of the eight scenarios has one $50 account shared across Chicago, Los Angeles, Miami and San Francisco. Cash cannot fall below $40, each entry costs at most $5 including modeled fees, and quantities are whole contracts. Candidates arrive at the same delayed timestamps as in the city study. Settlements are processed before entries at the same timestamp; simultaneous entries are prioritized by estimated dollar edge, with slug as a deterministic final tie-break. An earlier entry cannot spend a later settlement or use a later city's quote. Available cash can reduce a quantity or reject an entry if its resulting expected dollar edge is too small. No new coefficients, extra deposits, or larger risk budget are introduced.

`tools/run_us_portfolio.py PORTFOLIO_DIRECTORY TRANSFER_ANALYSIS_DIRECTORY` requires the completed, audited transfer report and frozen code hashes. It creates a new analysis directory and a graph showing both trading P&L and P&L after one prorated $200/month subscription expense per scenario. The graph displays both slippage settings. Its curves show realized scenario profit, not marked equity; open position basis is disclosed separately.

`tools/audit_us_portfolio.py ANALYSIS_DIRECTORY` independently reconstructs allocation from the audited per-city candidates and raw settlement responses. It checks timestamp and profit priority, shared cash, quantity sizing, fees, payouts, reserve, conservation, complete comparison arms and expense allocation. `tools/summarize_us_edge.py ANALYSIS_DIRECTORY` then adds estimated-edge and winner-concentration diagnostics. These calculations cannot establish executable historical fills or real future profit.

No scenario is added to another as a larger portfolio. The same calendar period across cities is correlated, not an independent time-period replication. Original New York backtests and the existing US forward-paper accounts remain unchanged.

## Completed results

Use `tools/run_us_portfolio_v2.py` after the documented station-field compatibility correction in `execution-amendment-v2.json`; original code and freezes are preserved. Analysis `data/us-portfolio/1789693764400920100/analysis-1789694958387478400` uses the original completed transfer analysis `analysis-1789694929447632400`. It passed 767 independent portfolio checks, plus the underlying 3,428 transfer checks. All positions closed.

| Strategy | Trading P&L | Half-cent slip P&L | After subscription | Half-cent slip after subscription |
|---|---:|---:|---:|---:|
| Benter | $8.10 | -$3.66 | -$56.34 | -$68.10 |
| Market recalibration, no forecast | $8.10 | -$4.93 | -$56.34 | -$69.37 |
| Raw market | $0.00 | $0.00 | -$64.44 | -$64.44 |
| MOS only | -$9.99 | -$10.00 | -$74.43 | -$74.44 |

Benter made 18 entries without added slippage and 15 with it. The no-forecast variant made 18 and 12. The raw-market baseline made no trades, so its zero is inactivity rather than demonstrated performance. The zero-slip Benter model estimated only $5.86 of total entry edge, about $0.61 per registered day. Its largest winner was $8.11; subtracting that winner from the realized total leaves -$0.01. That is a descriptive concentration check, not a resimulated alternative cash path. None of the arms covers the allocated subscription, and half-cent slippage makes both recalibration variants lose trading capital. No promotion to the frozen forward accounts is supported.

The dashboard exposes the complete comparison, both slippage settings, the profit/expense graph, and all separate-city arms. Browser checks at 1440px and 390px verified actual scenario changes, 16 city rows per selected cost, decoded charts, no console/page errors and no horizontal page overflow. The complete Python suite passes 137 tests.
