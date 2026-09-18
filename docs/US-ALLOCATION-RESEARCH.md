# US profit research: allocation and calibration

September 17, 2026. No paid model or data subscription is configured. Optimize expected dollars after trading costs, preserving one shared $50 account and $40 cash reserve.

## Primary research reviewed

Cardozo and Rivero-Wildemauwe, The Favorite-Longshot Bias in Prediction Markets (September 2026): https://arxiv.org/html/2609.12878v1

The study uses international Polymarket transaction data through March 2026, not our US gateway market sample. Weather results change sign with aggregation. Its hold-to-resolution returns omit transaction-specific fees and rebates and do not necessarily equal traders' realized profits. Implication for PolyLab: keep station-date groups intact, show shared-account dollars, fees and price stress, and avoid assuming that buying favorites or fading longshots is universally profitable. No coefficients or profit rates from this paper are imported into our US account.

## Catalogue methods reviewed

Calibration harvesting: https://www.polyresearchrobotics.com/strategies/brier-score-calibration-harvesting
Requires a large resolved sample and persistent probability calibration. Current US coefficients were fitted on just ten eligible NYC dates. The new allocator freezes the earlier market exponent, uses normalized complete outcome ladders and tests across five cities, but this does not establish persistence or improve probability estimation itself.

Stress allocation: https://www.polyresearchrobotics.com/strategies/scenario-stress-allocation-engine
This is a portfolio control rather than an alpha source. PolyLab already has scenario risk components; this cycle implements a different, clearly labeled expected-dollar allocation objective with a deterministic cash-loss bound. Worst possible simultaneous loss cannot consume the $40 reserve. A city option is one side of one contract, so correlated bands within that city are not treated as independent bets. Fees and half-cent execution stress are tested explicitly.

Station nowcasting: https://www.polyresearchrobotics.com/strategies/station-level-observation-nowcast
A plausible next information source is the exact resolving station's observed daily extreme and remaining heating window. METAR is a covariate, not automatically identical to the contractual CLI daily high. We need observed publication/receipt times and station-specific correction rules; retroactively assigning final daily observations to earlier trades would create an artificial edge. Prospective receipt collection remains the next data-quality priority.

## New implementation

Study data/us-allocation/1789695789406088400 registers all five US stations (KNYC, KMDW, KLAX, KMIA, KSFO), September 8-16. These outcomes were already seen in earlier experiments; this is retrospective allocation exploration, not a fresh holdout. Every city uses 02:15 UTC on the climate date. A multiple-choice knapsack maximizes model expected dollars, with at most one contract side per city and whole quantities. The equal-budget baseline uses the same signals and costs. At decision time we reserve allocations; delayed quotes may cancel or reduce them but cannot change the chosen contract or increase its planned quantity. No future settlement cash is available to earlier decisions. No model is refitted.

The collector reuses 378 verified source files and requests 162 missing common-time histories using the shared rate limiter. A dedicated independent audit validates source hashes, prices, fees, cash and chosen quantities, and verifies each optimized decision using a separate integer solver. None of these checks establish historical fill depth or forward profit.

Fee verification: https://docs.polymarket.us/fees was checked this cycle. The schedule effective September 17 uses taker coefficient 0.0695 times quantity times p times (1-p), rounded half-even to cents. This is a current-cost scenario on September 8-16 historical prices; no historical-fee equivalence is claimed. No maker rebate is credited without a simulated maker fill supported by appropriate data.

## Completed result

Analysis: `data/us-allocation/1789695789406088400/analysis-1789696699711406700`. All 270 histories and 270 settlement receipts are present; 39 of 45 station-dates have complete signal ladders. No collection errors. 2,802 audit checks pass, including independent integer optimization and fee/cash reconstruction. All positions closed.

| Allocation | No added slippage | Half-cent per side | Entries (zero / half-cent) |
|---|---:|---:|---:|
| Expected dollars | -$9.32 | -$9.53 | 9 / 9 |
| Equal budget | -$3.49 | -$1.11 | 11 / 10 |

The optimized zero-slip account ended at $40.68, with $40 reserved. Its model estimated about $3.31 of entry edge but realized -$9.32. Chicago contributed -$11.48, LA -$4.57 and Miami -$4.48; SF +$6.87 and NYC +$4.34 partly offset those losses. These city attributions reflect this shared-cash path, not independent city account returns or a validated future filter.

The stress arm can lose less than the zero-slip arm because price changes alter qualifying trades and quantities; these are separately simulated accounts, not a fixed-trade subtraction. This result rejects the idea that better dollar allocation alone fixes the current probability estimates. Do not promote this model, increase its risk budget or cherry-pick only its profitable cities. A materially different information source and prospective evaluation are needed.

Implementation: `polylab/us_allocation.py`; runner `tools/run_us_allocation.py`; audit `tools/audit_us_allocation.py`. Code and inputs are frozen in the study registration directory. Corrected trading-only chart uses `tools/render_us_trading_profit.py`; original plots/reports remain unchanged. Dashboard default tables exclude the erroneous inherited subscription assumption. 142 Python tests pass, including exhaustive optimizer checks and no-lookahead fixtures.
