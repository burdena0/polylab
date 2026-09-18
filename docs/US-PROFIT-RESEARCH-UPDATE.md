# Profit research: public account patterns and settlement costs

Snapshot: September 17, 2026 (local New York); source collection continues into September 18 UTC.

PolyLab's objective is maximum repeatable net dollars, with more than $5 on the $50 shared paper account as the minimum user target. It has no configured paid subscription. The target is not achieved in forward paper trading. Current research retains the $40 reserve and $5 entry cap. No purchases, hosting charges or real orders were made.

## Public account benchmark

Source archive: `data/public-weather-accounts/1789698204761899700`. The collector uses the official public international Data API. Selection was the union of the first three WEATHER accounts by ALL and MONTH PNL, with latest 50 closed positions and latest 200 trades per account. It does not select closed positions by profitability. All 14 response envelopes passed exact raw JSON/hash checks.

The live API ranks differed from the cached website's monthly table. The API snapshot controls this analysis; neither is silently merged with the other. These are international accounts, not Polymarket US accounts. No account is independently established to be a bot, and public PNL is not a bankroll ROI.

| Account in live API snapshot | Period | Reported weather PNL | Sample temperature buys | Median buy price | Buys at least 90 cents |
|---|---|---:|---:|---:|---:|
| gopfan2 | All time | $326,399.25 | 0 | unavailable | 0 |
| aenews2 | All time | $285,810.10 | 0 | unavailable | 0 |
| ColdMath | All time | $136,507.54 | 0 | unavailable | 0 |
| Bilberry | Month | $24,212.61 | 101 | 42.00 cents | 1 |
| 0x9c95...752db | Month | $16,834.17 | 167 | 23.00 cents | 0 |
| 0x9506...db1c4f | Month | $15,620.14 | 200 | 52.52 cents | 1 |

The all-time leaders' most recent trades in these bounded samples were outside temperature markets; this does not establish that they stopped trading weather. The three monthly leaders had 21, 26 and 25 distinct parsed cities in their 50 latest closed positions. Their trade samples included purchases in multiple bands of the same event in 25, 16 and 25 events respectively. Bilberry also had eight conditions with both buys and sells. These are observed patterns, not proof of market making, a forecast model or an agent.

Only 2 of 468 sampled temperature buys were priced at least 90 cents. This weakens near-certain-winner buying as an explanation for these accounts' current sampled activity. It does not establish entry time relative to resolution. Fragmented fills can also produce short trade gaps.

The original report's city parser retained temperature bands in the city labels. The corrected attribution in `analysis-1789698471873347200/report.json` preserves the original data and report. `sample_cost_proxy` is sum(totalBought * avgPrice), a turnover basis proxy; it must not be used as initial capital or ROI. Closed-position samples omit open risk, lifetime cash flows and full account costs. These rankings do not demonstrate that their profits are reproducible with $50 or on US contracts.

Primary documentation: [leaderboard API](https://docs.polymarket.com/api-reference/core/get-trader-leaderboard-rankings), [closed positions](https://docs.polymarket.com/api-reference/core/get-closed-positions-for-a-user), [activity](https://docs.polymarket.com/api-reference/core/get-user-activity). Exact successful request URLs and receipts are in each source envelope.

## Near-settlement test

Implemented `polylab/us_endgame.py` and `tools/run_us_endgame.py`. This new screen permits a one-sided book when the side needed to enter has depth; it still requires an open market, actual information receipt before the quote request, completed daily CLI, freshness bounds, whole contracts, depth cap and positive conditional margin. Existing frozen strategies were not changed.

Result: `data/us-endgame/1789698403505710000/report.json`, drawn from 31 completed prospective CLI passes and 74 quote receipts. **Zero qualified quotes, zero positions.** All 74 lacked required-side liquidity and all used incomplete daily CLI readings. Seventy-one also failed the exchange timestamp gate and 16 failed the HTTP-age bound. Those timestamp gates are conservative research rules, not assertions that the exchange defines transactTime as book generation time. The full CLI source audit passed 992 checks with no collection errors.

This is a retrospective screen of recorded quotes. It is not a profitable backtest, and the cost grid is an analytical sensitivity rather than a forecast or paper ledger. Complete-day information still needs to be observed prospectively during the registered collection period.

At a quoted 90 cents, five contracts cost $4.53 including the aggregate fee bound. A $1 payout yields $0.47; at a hypothetical true payout probability of 95%, expected profit is $0.22. At 99 cents, five contracts cost $4.95, yield $0.05 if correct and lose $4.95 if wrong. More than $5 requires 101 identical all-winning batches at 99 cents before slippage; this is arithmetic, not an achievable turnover forecast. Half-cent slippage reduces that conditional five-contract profit to $0.025. Per-position returns must not be confused with returns on the whole $50 account.

[US fees](https://docs.polymarket.us/fees) are included with Decimal half-even rounding and the existing conservative aggregate fee bound. Corrections, unavailable fills and payout delay remain material unknowns. No assumed probability from the sensitivity grid is used to open positions.

The corrected graph is `data/us-endgame/1789698403505710000/render-1789698471417998700/cost-sensitivity.png`. Its audit independently checks 288 cost/profit identities and all four nine-point scenario groups. The first frozen renderer compared decimal strings and omitted three curves; it is retained as superseded evidence. The new renderer fixes grouping numerically without changing scenario calculations. The corrected rendered output was visually inspected.

## Feed and runtime

Original station-feed study `data/us-station-feed/1789697787589399700` was stopped after four NWS responses omitted rawMessage. This is legitimate source behavior. The original files and stop reason are preserved.

Version 2, `data/us-station-feed-v2/1789698109067867000`, retains those records as source-specific observations with no cross-provider METAR identity. Only nonempty matching raw reports match across providers. It has completed six clean paired passes across all five stations; 66 raw-receipt and matching checks passed. Its process and the CLI collector were verified running. Both retain their September 19 16:00 UTC stop, data caps and no-order scope. All 158 unit tests pass.

Bare-metal hosting is not supported by the current evidence. Native local execution already runs on Windows. Missing liquidity and upstream publication/cache delays dominate the opportunities sampled so far; a faster CPU cannot reconstruct unavailable offers. No paid hosting is authorized or required for this study.

## Next experiment

Test multiple bands per city and buy/sell timing as new, frozen US experiments using untouched timestamps and one shared account. The leaderboard is a hypothesis source only; do not copy foreign fills or assume their information was available locally. Compare against the existing one-band allocator and no-trade baseline, include fees/slippage, and attribute gains by event and day to expose concentration. Do not promote the previously losing market-recalibration model just because it can be allocated more broadly.

Continue the current prospective CLI/feed capture through its registered horizon, then evaluate complete-day information and earlier observations against the actual required side of later books. Preserve all losing results and the separate SupahTrade halt. Higher net profit remains an unachieved research objective.
