# Archived MOS calibration and US weather profit pilot

## Evidence

- Forecast/CLI archive: data/us-mos/1789689723727704700. Fifteen source files: GFS and NAM MOS JSON plus original CLI ZIP bulletins for each of five US stations.
- Calibration: data/us-mos/1789689723727704700/calibration-1789689900234570400/report.json. 255 station-days; 30 training days, five validation dates and 16 later test dates per station. The first validation date is excluded where the completed training CLI was not yet available at the proposed decision time.
- Frozen US price sample: data/us-weather-history/1789689723559279700. Six first-available NYC September dates, selected before downloading 36 histories and 36 settlement values. Collection finished with all 72 response files.
- Profit replay: data/us-weather-history/1789689723559279700/replay-1789690477552828700/report.json and weather-profit.png. All sources and dependent code hashes are recorded. Every plotted scenario uses the same period, including the zero-trade baseline.

US search did not reliably honor the closed-status request. The tagged event endpoint with tagSlug=weather and closed=true returned genuine closed weather events, including 75 events in the September date window. Response status and dates were checked locally. September 2 was absent from that response; it was not invented or substituted.

## Calibration

The feature is the maximum of hourly-interpolated GFS and NAM temperatures over the fixed-standard-time climate day. It is not a claimed continuous station maximum. Only the previous calendar date's 12Z forecast cycle is used. MOS JSON timestamps are documented as UTC; publication availability is conservatively assumed at runtime plus six hours because original receipt timestamps are not supplied.

For each station, the forecast is the mean of its GFS and NAM sampled highs, corrected by the mean training error. The residual standard deviation is fitted on the same training dates with a fixed 1F minimum. A normal residual distribution maps temperature thresholds to probabilities. This is a deterministic MOS calibration, not calibration of the separate GFS/ECMWF/ICON ensemble archive.

Training: July 28–August 26. Validation: August 27–31. Temperature test: September 1–16. Original complete CLI reports are read from their observed-value columns; afternoon products, missing values and later corrections do not replace the earliest complete report. One interim Miami product lacked a usable maximum and was rejected. No temperature test result was used to refit coefficients.

| Station | Test days | Raw GFS RMSE (F) | Corrected blend RMSE (F) |
| --- | ---: | ---: | ---: |
| KNYC | 16 | 2.15 | 1.93 |
| KSFO | 16 | 4.84 | 4.02 |
| KMIA | 16 | 3.06 | 1.88 |
| KMDW | 16 | 2.35 | 1.90 |
| KLAX | 16 | 4.57 | 2.70 |

This is forecast-skill evidence, not profit evidence. In particular, tail probabilities can remain poorly calibrated despite lower RMSE.

## Profit replay

The six NYC dates are September 1, 3, 4, 5, 6 and 7. The strategy selects one highest estimated dollar-edge contract/side per day six hours before the climate day starts. All six market bands must have contemporaneous price observations. The actual simulated entry uses a later quote at least 60 seconds after the decision; if the expected dollar edge falls below $0.10 before entry, the trade is rejected. It never switches to a different contract using future prices.

Each scenario starts with $50, preserves $40 cash and spends at most $5 per entry. Quantities are whole contracts, with no claim of historical depth sufficient to fill them. Global event ordering keeps cash tied up across overlapping daily positions. Settlement values are verified by exact US slug; cash release at next-day 11 AM ET (or later complete CLI issuance) is an explicit simulation timing assumption.

There are 2,629 usable price observations and 36 verified payouts. September 1 has an unusable outer-band history, and September 6 has no usable prices in the requested window. These two dates have no entries. Both corrected and uncorrected forecast variants made three entries, lost $10 and ended at $40 cash with no open positions. Added half-cent slippage also exhausted the same risk budget. A normalized market-price baseline made zero entries; this is not a profitable strategy.

The experiment applies the September 17 fee curve to earlier prices as a current-cost counterfactual, not reconstructed historical fees. A prorated $200/month subscription over the common pilot window adds $51.11 overhead per independent scenario. Forecast variants therefore show -$61.11 after that expense. The trading account and external subscription are kept separate so reserve accounting remains clear.

No strategy is promoted. The pilot includes losses in low-price outcomes where model tail probabilities materially exceeded market prices. The next research step should use new data and examine probability calibration or a Benter-style model/market combination, not resize or retune this same losing pilot into an apparent success.

## Reproduction and sources

Run `tools/collect_mos_calibration.py`, prepare its archive with `polylab.us_mos.prepare`, and collect a registered US pilot with `tools/collect_us_weather_history.py`. Existing partial collections resume only from their original directory. Run `tools/run_us_weather_replay.py HISTORY_DIRECTORY CALIBRATION_DIRECTORY` after collection is complete. Each analysis creates a new immutable output directory.

- [IEM MOS archive](https://mesonet.agron.iastate.edu/mos/fe.phtml)
- [MOS download API](https://mesonet.agron.iastate.edu/cgi-bin/request/mos.py?help)
- [Original NWS text archive API](https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py?help)
- [US tagged event endpoint](https://docs.polymarket.us/api-reference/events/get-events)
- [US historical prices](https://docs.polymarket.us/api-reference/price-history/get-price-history)
- [US fees](https://docs.polymarket.us/fees)
