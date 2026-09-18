# Prospective US CLI information study

Registered study: `data/us-cli-edge/1789697178863031400`.

A new source of information is being tested after the five-city probability-recalibration allocator lost money. The hypothesis is that received official station observations can constrain weather outcomes before displayed prices fully adjust. This study collects evidence; it has no order client or paper positions and assigns no calibrated probability to a CLI reading remaining unchanged.

The collector rotates New York, Chicago, Miami, Los Angeles and San Francisco. Each pass saves three CLI products, the latest NWS METAR covariate, and up to six relevant US books. Exact original NWS JSON bytes, local request/receipt times, source hashes, CLI issuance times and changes are retained. A first observation is a baseline, not evidence of publication lead. Versions sharing an issuance time but conflicting in value fail closed. Only information actually received before a quote request can create a research signal.

An interim daily maximum can exclude strictly lower upper-bounded bands; it does not identify the final winning band. A reached open upper tail can become conditionally certain. Daily minimum logic is reversed. A complete-day CLI yields a conditional band classification, but revisions and the exchange's settlement/review rules remain relevant. METAR is saved separately and is not silently substituted for CLI.

The conditional margin assumes a one-dollar payoff and deducts modeled fees and half-cent slippage. It is neither expected profit nor realized profit. Sizes are limited to whole contracts, $5 cost and 25% of observed top depth. The registered research qualification also requires an open two-sided book, explicit HTTP-age evidence within 45 seconds and an exchange timestamp within five seconds. HTTP response age and exchange update time are separate concepts. Public documentation does not establish that every old transactTime means an unavailable order; however, all first-cycle samples also lacked liquidity on the needed side, independently preventing the proposed trade.

## Verified initial evidence

Audit `audit-1789697419837335000` passed 197 checks across six completed passes, all five cities, 15 unique CLI versions and 14 book observations. All 14 lacked the required side of the book; zero qualified research quotes and zero positions. This baseline does not establish a profitable information edge. The next analysis compares subsequent received versions and later quotes without backdating availability.

148 Python unit tests pass. `tools/audit_us_cli_edge.py` verifies completed immutable passes while the collector remains running, checks original NWS byte hashes and local chronology, and compares repeated quotes for the same received CLI version. Open/incomplete passes are excluded from that audit and remain visible as start records.

## Runtime and continuation

The collector was confirmed live as process 42824 and exec session 57120 at approximately September 17, 22:10 ET. Reverify the process/session before assuming it remains live. Do not duplicate or restart it based only on a stale state file. Command: `.venv/Scripts/python.exe tools/collect_us_cli_edge.py data/us-cli-edge/1789697178863031400 --loop`.

Each pass has a 235-second work budget, a 30-second pause, shared US gateway pacing, and a study-wide 500 MB archive cap. The registered stop is September 19, 2026 at 16:00 UTC (noon ET), after the two registered climate dates' expected settlement windows. A local file lock serializes overlapping invocations. No subscription, scheduled task, account or paid service was added. The existing frozen US paper worker and separate SupahTrade halt remain unchanged.

Source references:

- https://docs.polymarket.us/faqs/weather-faqs — station mappings, CLI settlement and discrepancy review.
- https://www.weather.gov/documentation/services-web-api — public API, cache behavior and delayed observations.
- https://docs.polymarket.us/api-reference/markets/get-market-book — public US book endpoint and fields.
- https://docs.polymarket.us/trader-guide/market-data — institutional snapshots/update behavior; authenticated streaming is distinct from this public REST archive.

Next work: audit newly completed passes, compare actual received publication changes with quote availability, and evaluate faster official station observations as separately labeled covariates if CLI reports arrive after usable liquidity disappears. Do not retrofit final daily extremes into earlier timestamps or promote the current zero-opportunity baseline as a successful strategy.
