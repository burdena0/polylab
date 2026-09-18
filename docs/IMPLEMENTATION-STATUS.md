# Implementation status — scope remains the full requested library

The previous goal turn delivered a working dashboard, research pipeline, local agent comparison, paper workers and weather archive. This continuation adds executable basket logic and a separate replay engine; it is progress, not goal completion.

As of 17 September 2026, the 303-row dashboard contains the 297 source strategies plus six local paper methods:

| Capability label | Entries | Meaning |
|---|---:|---|
| Backtest adapter | 11 | Existing single-market research rules with BTC replay |
| Basket replay + evaluator | 4 | Executable binary basket checks and delayed BTC replay |
| Basket evaluator | 10 | Executable settlement-payoff checks; historical multi-market data/relationship verification still required |
| Quote formula only | 1 | Quote generation; passive fills unproven |
| Forward paper only | 1 | Guide's fifteen-minute underlying-price signal |
| Risk module | 8 | Executable allocation, liquidity, correlation, scenario, netting and drawdown controls |
| Temperature ensemble component | 2 | Partial temperature implementation; calibration, other weather types and profit replay incomplete |
| Research specification | 266 | Not implemented |

An executable evaluator is a component, not a claim that every operational requirement from its source page is complete. These entries share mathematically appropriate primitives; their counts are not independent alpha strategies. The goal remains active.

## Basket strategies added

`polylab/coherence.py` registers fourteen source entries: the existing Yes/No complement method; split/merge redemption; merge/split set completion; gas-fee threshold; multi-outcome overround; cross-market mutually exclusive fade; count buckets; mutually exclusive first-to-ship; awards Dutch books; strike ladders; temperature ladders; nested deadlines; nominee-to-winner implication; and approval-indication implication.

The engine enforces condition/token identity, non-crossed books, quote timestamps/skew, fees/slippage/fixed-cost budgets, conservative depth participation, and venue minimum sizes. Multi-market recipes require explicit shared settlement definitions and supplied verification evidence. Integer partitions reject gaps, overlaps and missing tails. No semantic implication is inferred from similar names. Approval in a second indication is not automatically assumed to imply approval in a first indication.

Corrected source errors:

- Buy YES and NO at **asks** and merge when net cost is below one; split funded collateral and sell at **bids** when net receipts exceed one. The linked CTF prose reverses these directions.
- A basket of N NO shares in an exhaustive one-winner partition pays **N−1**, not one. A sum of YES prices alone does not prove the NO basket is cheap after the actual spreads.
- Overlapping threshold contracts are nested events, not mutually exclusive buckets. Monotonicity equality by itself is not an arbitrage.

The payoff logic follows [Polymarket's position operations](https://docs.polymarket.com/trading/positions/manage). No transaction signing, chain conversion, wallet connection or real order placement is implemented or authorized here. The calculated conditional payout floor is never displayed as realized P&L. Multi-leg fill and semantic-verification risks remain.

## Replay evidence

`polylab/coherence_replay.py` evaluates four binary variants on the last 120 selected BTC markets. A signal at 60 seconds commits direction and maximum size; a later quote at least one second afterward must still satisfy the cost/depth gates. It cannot switch direction using future information. Results use an explicitly hypothetical simultaneous-fill/immediate-conversion model and configurable fixed gas cost.

Default run `20260917T222004-78965b`: zero qualifying conversions in each variant. 25 markets were rejected for minimum/depth constraints, and 95 for insufficient net edge. Strict freshness run `20260917T222003-c90bb2` rejected all 120 observations for unknown historical exchange timestamps. Every run has its own immutable report in `data/coherence-runs`. Further reruns may change the latest pointer, not these reports.

The live workbench also successfully loaded and evaluated one actual weather pair; the observed result was rejection for venue minimum/depth. This checks the live input path, not profitability.

## Validation and remaining work

The expanded suite has 91 tests, including independent payoff enumeration, risk allocation and covariance checks, causal delayed exits, paired paper-account failure handling, current fee cash accounting, station URL identity, oracle timestamps, external-spot feature causality, weather daily-member counts, DST, calibration chronology and source-review integrity. All passed on 17 September 2026.

Browser flow checked at 1536×1024 and 390×844: deep link → binary example evaluation → replay rerun → three-outcome NO payoff → reject non-exhaustive input → open temperature evaluator from the library. No page errors or horizontal document overflow. Browser plugin was absent; installed Chrome via bundled Playwright was used. Screenshots and the machine-readable QA receipt are under the thread's external visualization directory.

Still required for the full objective: implement the remaining 266 specifications, complete the two partial temperature components, obtain/collect appropriate point-in-time inputs, verify market relationships and settlement definitions, and backtest those implementations with their actual execution constraints. The present evaluators do not replace those missing data integrations. Prospective paper profitability and full weather forecast-edge testing also remain unproven.

## Net-profit continuation

The preregistered 1,200-condition study (`data/profit-study-v1/runs/1789684510741440600`) failed to reproduce the small-sample exit-depth profit. Baseline: −$14.82; exit-depth: −$14.53; volatility: −$7.05; drawdown: −$4.11; combined: −$3.43; half Kelly: no entries. Each account starts at $50. All final locked basis is zero. Fees are historical assumptions, not reconstructed historical truth. These are previously unused conditions in the same market regime, not an independent period.

The new external-price models use 132,480 checksum-verified one-minute Binance candles. Temporal feature tests pass. Gaussian, fundamental and Benter variants all lost money on validation; no candidate is approved and further holdout data is preserved. New source collection is running for exact-rule weather stations and live Chainlink TWAPs.

Current paper experiments use separate `fee-v2` accounts, actual Gamma feeSchedule receipts, the current taker curve, and rounded fees in the cash/trade ledger. Their initial verified snapshot is zero P&L and no open positions. The preceding flat-fee state and source files are preserved under `data/paper-fee-transition/1789685271640641800`. Four independent paper accounts are running; only the paired momentum arms share an identical feed. The earlier agent/no-agent historical comparison remains separate.
