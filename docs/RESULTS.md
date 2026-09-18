# PolyLab results — 17 September 2026

Default reproducible run: `20260917T220630-922448`. See its immutable `data/runs/<id>/report.json` and the cost-sensitivity/live-feed receipt `data/release-validation.json`.

## Historical replay

600 verified markets; 180,000 observations; 120 evaluation markets. Separate $50 accounts. Hypothetical fills and assumed costs; no live profitability claim.

| Method | Entries | Realized P&L | Unexited cost basis |
|---|---:|---:|---:|
| Momentum | 19 | -$2.77 | $0.00 |
| Mean reversion | 12 | -$5.79 | $2.23 |
| Crowd fade | 32 | -$8.10 | $0.00 |
| Base rate | 27 | -$4.15 | $0.00 |
| Ensemble | 1 | -$0.99 | $0.00 |
| Book-feature model | 19 | -$6.11 | $0.00 |
| Benter, Shin, normalization, calibration, OFI and complement | 0 each | $0.00 | $0.00 |

Zero trades is not evidence of profitability. Unsold basis is excluded from realized P&L and marked at zero in the equity curve. None of these results justifies live deployment.

Momentum remains negative in both cost stress cases: -$1.60 with zero fees but retained slippage, -$3.65 with 200 bps fees. Strict historical freshness rejects every entry because historical exchange quote age is unavailable. These runs are retained separately.

## Agent versus no agent

Matched 60-market momentum comparison:

| Variant | Entries | Realized P&L |
|---|---:|---:|
| No agent | 14 | -$1.38 |
| Qwen3.5:9b veto | 3 | -$0.10 |
| Agent with measured delay | 4 | -$0.27 |
| Simple spread/volatility filter | 8 | -$0.63 |

The no-delay difference is +$1.28, with exploratory paired 95% bootstrap interval **-$2.88 to +$5.17**. This does not establish a reliable agent advantage. The earlier Benter experiment had zero entries in either arm and remains separately available.

Qwen3.5:9b fit entirely in the RTX A4000 GPU. Two warm two-case schema checks each took approximately 1.11 seconds; the first included model loading and took about 23 seconds. The actual five-market experiment batches averaged 3.42 seconds. These are workload-specific speed measurements, not evidence that this model forecasts better than a larger model. The earlier 27B run spilled into CPU memory; its cold-call timing is not an apples-to-apples quality or latency benchmark.

## Probability papers

Evaluation Brier scores: normalization 0.20215; Shin 0.20202; book-feature model 0.21190; Benter 0.20585. Shin's difference is tiny; Benter did not improve on market normalization in this sample. Forecast scores and trading returns answer different questions.

## Forward capture

At the release receipt, the weather stream was connected with **84,016 snapshots, seven city-day files, and 118 initialized outcome books**. Counts continue growing. A Dallas gzip download contained 15,664 parseable rows, including 3,592 passing the freshness gate. Its first snapshot contained 10 bid and 13 ask levels. The archive backtest returned insufficient fresh decision history; it did not invent a performance graph from stale data.

Both independent paper workers were running. Each still held $50 cash with no positions and $0 realized P&L. The guide account successfully consumed a fresh Coinbase observation and skipped an entry below its edge threshold. These are early operational checks, not a completed prospective profitability experiment.

The broader library remains incomplete: 297 descriptions are searchable, but only the declared research adapters execute. Forecast-edge weather testing, full oracle-history replication, passive market-making fills and the remaining specialized strategies need additional implementations and appropriate point-in-time data.
