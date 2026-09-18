> Cost correction (September 17): No paid model/data subscription is configured for PolyLab. The inherited $200/month is a legacy hypothetical sensitivity, not an actual bill. Current profit excludes this deduction; fees and slippage remain. Frozen historical artifacts retain their original assumptions for reproducibility.

# Frozen US probability transfer study

The New York Benter-style price scenario earned $17.25 after trading fees but lost $47.19 after allocated subscription. Its fitted weights gave almost no weight to the weather forecast. This study tests that lead on all four other US stations in the available event archive: KMDW, KLAX, KMIA and KSFO. It does not increase position size or tune the profitable New York dates.

Registration: `data/us-transfer/1789692627926092500/registration.json`, created before collecting the 432 price/settlement responses for 36 station-dates. Every available September 8–16 date in the four stations is included. These share the New York test's calendar period and therefore common weather/regime dependence; they are new contracts, not an independent temporal replication. Earlier temperature-error summaries included these stations, but their price histories and profitability had not been inspected at registration.

Four arms are registered, each with zero and half-cent slippage: frozen Benter weights, market recalibration with alpha set to zero and beta unchanged, normalized market probabilities, and station-calibrated MOS probabilities. Only station bias/spread uses the original July 28–August 16 training dates. Benter weights are never refitted. Each city/strategy/cost scenario independently starts with $50 and a $40 reserve, with at most $5 per entry and separately allocated $200/month expense. They must not be summed as one portfolio. Signal, delay, coverage, fee and settlement-timing rules follow the original US study.

Collection is bounded and resumable with `tools/collect_us_weather_history.py DIRECTORY`; it uses the same shared US transport gate. After all registered requests finish, `tools/run_us_transfer.py DIRECTORY` produces immutable JSON and separate zero-slip and added-slip four-city graphs. All registered arms, cities and coverage gaps must be reported, including losses. The original New York results and paper accounts remain unchanged. No forward or live promotion follows from this test alone.

The public-book depth probe is separate: `tools/probe_us_forward_depth.py` records two snapshots at least 60 seconds apart for the earliest still-future daily decision ladder in cached US discovery. It holds a signal candidate's probability and direction fixed when checking the later quote, caps quantity at 25% of observed top depth and $5 cost, and records no position or realized profit. Its cache-based classification is explicitly distinct from the original five-second exchange-timestamp gate. Missing Age/Date headers remain unqualified. Advertised cache freshness is not a guarantee of an executable quote.

The completed probe is `data/us-forward-depth/1789692904970493000/report.json`, covering the September 18 Los Angeles ladder. Both rounds produced the same model-dependent candidate: five short contracts on the 81F-or-above band at $0.87, with displayed top depth 37.06 and estimated $0.215 profit after the modeled fee. This is expected value, not earned profit. Both rounds failed the cache classification; the first six-book collection spanned more than 45 seconds, and three of the twelve responses omitted Age despite reporting cache HIT. Both rounds also failed the original five-second exchange timestamp classification. No positions were opened.

Run `tools/audit_us_transfer.py ANALYSIS_DIRECTORY` after the completed transfer analysis. It separately reconciles all 32 city/strategy/cost accounts, source hashes, frozen model weights, the alpha-only ablation, training partitions, fees, settlements, cash reserve, subscription expense and probability scores. A passing arithmetic audit does not establish historical executable fills or prospective profit.

## Completed results

All 432 requests completed without collection errors: 14,981 usable prices, 216 payouts, and complete signals for 30 of 36 station-dates. The original runner failed before P&L computation because the multi-city registration's redundant station field collided with the frozen single-city loader. `execution-amendment-v2.json` records a compatibility adapter that validates and removes only that redundant key. Original code and freezes remain intact; strategy parameters and inputs are unchanged. Use `tools/run_us_transfer_v2.py` for reproduction.

The first completed analysis is `analysis-1789694929447632400`; the displayed version is `analysis-1789695065918496100`. The latter changes Matplotlib's dollar-sign text rendering only, and all results, coverage and source hashes were asserted equal to the first. Its `render-settings.json` records the setting. Both passed 3,428 audit checks. All positions closed.

| City | Benter, trading | Benter, half-cent slip | No-forecast recalibration, trading | No-forecast recalibration, half-cent slip |
|---|---:|---:|---:|---:|
| Chicago Midway | $3.10 | -$8.69 | $3.10 | -$8.69 |
| Los Angeles | $1.52 | $1.07 | $1.52 | -$3.23 |
| Miami | -$4.61 | -$4.86 | -$4.61 | -$4.86 |
| San Francisco | $18.30 | $13.13 | $18.30 | $13.13 |

These are independent $50 accounts. Every row remains negative after its allocated subscription, including San Francisco (-$45.31 without added slippage, -$50.48 with it). Raw-market baselines made no trades; MOS-only variants lost money in every city/cost case. Removing the tiny forecast weight leaves all zero-slip trades unchanged, but marginal entry thresholds produce different Los Angeles trades under added slippage. This does not demonstrate a weather-information edge. Selecting only San Francisco now would be selecting on known test outcomes and needs a new prospective test.
