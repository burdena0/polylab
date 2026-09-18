# US feasibility and forward experiment

## Frozen display-price sample

`data/us-history/1789687853207852500/registration.json` selected 24 markets before price/outcome downloads, using category round robin and SHA256 slug order from a bounded 60-market discovery batch. Selection required closed markets with end dates after the September 17 US fee change. This is a feasibility sample with selection bias, not independent validation.

The collector saved 1,109 raw historical points and 13 verified settlement values. Eleven settlement endpoints returned 404; closed metadata alone is not settlement proof. Normalization rejects invalid/crossed/out-of-range points and conflicting timestamps. Anonymous history responses are bound to slugs through their request receipts. Outcome values never enter signals or exits.

Registered rules: 15-minute momentum or opposing mean reversion, a two-cent move threshold, entry at a later observation at least 60 seconds after the signal, a 30-minute hold, and at most five minutes waiting for a target quote. Both long and short prices preserve the US single-instrument bid/ask spread. Each variant has independent $50 capital, $40 reserve and at most $5 per entry; the entire portfolio shares its reserve. Quantities are whole simulated contracts. Fees use the documented .0695 coefficient and half-even cents, conservatively capped using aggregate exact fees. No maker rebates.

The corrected replay is `replay-1789688325246200900` under that sample directory. Earlier intermediate replays remain preserved. Code hashes, receipts, normalized coverage, ledgers and assumptions are in report.json. Current realized trading results, before subscription overhead:

| Rule | Added slippage per side | Entries / exits | P&L | Fees |
| --- | ---: | ---: | ---: | ---: |
| Momentum | $0 | 3 / 3 | -$9.69 | $0.83 |
| Mean reversion | $0 | 1 / 1 | -$4.11 | $0.35 |
| Momentum | $0.005 | 3 / 3 | -$9.92 | $0.74 |
| Mean reversion | $0.005 | 1 / 1 | -$4.30 | $0.34 |

All positions closed in this replay. The prorated $200/month subscription adds about $5.42 expense over the sampled window, using a 30-day month. Current fee history is valid only after its effective time. Historical display prices lack depth, matching fills and original receipt availability, so these numbers are price-based scenarios, not verified executable returns. Do not retune this sample and call the result an untouched holdout.

Reproduce: `.venv\Scripts\python.exe tools/run_us_replay.py data/us-history/1789687853207852500`. Each run creates a new directory. The dashboard reads data/us-replay-latest.json and serves the report and realized P&L graph.

## Separate forward paper

`data/us-paper-v1/registration.json` freezes six US-listed contracts, including climate and sports, before forward signals. The registry, state and raw observations are separate from historical and international records. Two independent accounts start at $50 with $40 reserves. The initial runtime verification confirmed both accounts at zero trades and $50 cash.

The engine needs fresh observations spanning 15 minutes, then a later fresh book at least two seconds after its signal and within 90 seconds. Exchange timestamps must be no more than five seconds old; books must be open, two-sided and uncrossed. Whole simulated quantities use at most 25% of top depth, including fractional displayed depth rounded down for sizing. Entries are limited to one per registered contract per strategy. Exits occur after 30 minutes when enough fresh top depth exists, or after a verified settlement receipt. Unknown intervening depth and queue behavior remain fill uncertainty.

US paper runs for a bounded 24-hour observation session. On stop, any open positions remain recorded, not silently liquidated. Code hashes prevent restarting changed strategy code into the same experiment. Use a new experiment root for a changed configuration. Runtime controls are on the US page and at /api/us/paper/start and /api/us/paper/stop; all actions are local paper controls, never exchange orders.

An exploratory US agent comparison now exists (US-AGENT.md), and the US CLI/ensemble component is implemented (US-WEATHER.md). Independent agent validation, broader strategy implementations, historical full-book validation and demonstrated profitability remain unfinished. The negative feasibility screen does not justify live promotion.
