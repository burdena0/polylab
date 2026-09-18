# Methodology and evidence limits

## BTC archive

Downloaded the Kacho public BTC five-minute archive afresh at Hugging Face revision `42d917dc8e3205dde8ac909792af0cce2d715c9f`. Selected 600 market indices evenly across time, without selecting outcomes. Matched all 600 to closed CLOB market records by exact condition, slug and outcome tokens. Labels come from those CLOB winner flags rather than the archive's inferred labels. The selected data contains 180,000 sampled observations.

Chronological splits are 60% fundamental fitting, 20% combination calibration and 20% evaluation, with one-day embargoes at the boundaries. Valid effective sample sizes are 349, 109 and 120. Final labels are verified now; their historical publication timestamps are unavailable, so the embargo is an assumption rather than proof of point-in-time label availability.

Decisions occur 60 seconds after the market begins. Features use the last 20 valid observations available by that time, with no gaps above two seconds. Entry uses a later quote, at least one second after the signal; exit intent also requires a later quote. Displayed entry size is capped at 25%. Exit size must be available at the later quote. Default costs are assumptions, not reconstructed historical venue fees. No passive queue fills or settlement payouts are inferred. Unexited inventory stays locked with zero mark and its cost basis is disclosed separately from realized P&L.

The historical source contains cached top-of-book quotes, not exchange event timestamps or all intervening depth. Normal replay allows this unknown freshness only as an analytical simulation. Strict-freshness replay rejects every historical entry. No backtest is eligible for execution. Each strategy is an independent $50 account; totals across strategies are not a portfolio.

## Paper adaptations

Štrumbelj's paper motivates solving Shin's bookmaker-margin equation and comparing it against normalization. The paper's three-outcome odds example is a regression test. Underround cases are rejected for Shin rather than silently fitted. Exchange asks do not necessarily meet bookmaker assumptions; this is explicitly an adaptation.

Benter's combined model uses probabilities proportional to `fundamental^alpha * public^beta`, with alpha and beta fitted by log likelihood on a separate calibration period. A logistic model of book features replaces horse-specific fundamentals. Fundamental fitting, combination fitting and evaluation are separate. This is not a reproduction of horse-racing profits, exotic bet pricing, or a complete racing model.

Additional implemented rules include momentum, mean reversion, crowd fade, base rate, calibration, an ensemble, sampled order-flow imbalance, and an idealized collateralized complement scan. Numeric rule parameters are visible in `polylab/research.py`; the source catalogue provides prose, not identical runnable code. Cont's OFI formula is applied to sampled quotes, which is weaker than complete event-flow data. Avellaneda–Stoikov produces inventory-sensitive quotes only because trade events and queue evidence are missing.

## Agent experiment

The local Ollama model `qwen3.5:9b` receives anonymous numeric information available at decision time. Packets exclude dates, market identity, realized outcomes and future prices. Temperature is zero, seed 731, reasoning mode disabled, JSON schema constrained. The agent may veto a model signal; it cannot invent probabilities, resize orders or place exchange orders. Missing/invalid decisions reject entry.

Both experiments use the first 60 evaluation markets, selected before inference. The Benter experiment produced zero trades with or without the agent. A separately disclosed momentum experiment produces a nontrivial comparison. The dashboard compares the same account and costs with no agent, agent vetoes, vetoes plus measured batch delay, and a simple spread/volatility filter. Twelve five-market calls yielded 60 valid decisions. Latency is measured per batch, not per generated token.

The paired bootstrap is exploratory and resamples per-market equity increments. It is not a day-block bootstrap, does not correct for multiple experiments or serial dependence, and is not a formal probability-of-backtest-overfitting calculation. The interval includes zero. The evidence does not establish a general agent advantage.

## Forward paper accounts

Benter runs on live five-minute BTC books. The guide account uses fifteen-minute BTC markets and the guide's public Coinbase fallback for an underlying momentum heuristic. Coinbase is not the Chainlink settlement oracle. The heuristic is not a calibrated probability model. Books must be fresh and valid; an intention is filled only on a later fresh observation with adequate displayed size. Time exit intent is one minute before market end. Old unresolved positions remain locked rather than receiving invented settlement proceeds. State and journals persist locally.

The historical five-minute archive cannot reproduce the guide's fifteen-minute underlying signal. The guide is forward-paper-only until suitable point-in-time underlying/oracle history is collected. Paper accounts currently do not run the LLM; the agent is an experimental backtest veto, not a promoted execution controller.

## Weather archive

Discovery is bounded to the first 100 weather events and at most 128 outcome tokens. Region groups distribute selected complete events; this is a selected sample, not all markets in a region. Only daily high/low temperature markets are included. Each stream starts from a full book, applies price-level updates, removes zero sizes, checks condition/token mapping, and invalidates books on disconnect or out-of-order updates. Snapshots preserve source timestamps and all captured price levels. The UI displays the first 30 levels on each side; downloads contain all levels.

The one-second cadence is best effort. An unchanged book retains its exchange timestamp; it is not made fresh by a new local snapshot. A five-second age gate is conservative and may exclude an unchanged but still valid book. Reconnect counters, timestamps and absent intervals expose gaps. Capture stops at a 2 GB archive budget. Only data recorded while this machine is awake and connected is available.

Weather replay backtesting selects the first condition by identifier, pairs Yes/No snapshots, and divides its history into five-minute windows. It reuses momentum and mean reversion with strict freshness, without a weather forecast signal or settlement payouts. Stale observations break eligibility. An insufficient-data response is a valid refusal to fabricate returns. This does not establish temperature-distribution or forecast-edge strategies: archived forecasts, settlement rules and verified station observations are still needed for those.

## References

- [PR&R guide](https://www.polyresearchrobotics.com/guide/how-to-build-a-polymarket-trading-bot)
- [PR&R strategy catalogue](https://www.polyresearchrobotics.com/strategies)
- [Source archive](https://huggingface.co/datasets/kachoio/polymarket-5-minute-crypto-up-down-markets)
- [Polymarket realtime market data](https://docs.polymarket.com/market-data/realtime-data)
- User-supplied `On determining probability forecasts from betting odds.pdf` and `benter_paper-3.pdf`; extracted reference text is retained in this directory.
- [Cont, Kukanov & Stoikov](https://arxiv.org/abs/1011.6402)
- [Avellaneda & Stoikov](https://math.nyu.edu/inmemoriam/avellaneda/HighFrequencyTrading.pdf)
- [Bailey et al. on backtest overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
- [Qwen3.5 on Ollama](https://ollama.com/library/qwen3.5)
