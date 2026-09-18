> Cost correction (September 17): No paid model/data subscription is configured for PolyLab. The inherited $200/month is a legacy hypothetical sensitivity, not an actual bill. Current profit excludes this deduction; fees and slippage remain. Frozen historical artifacts retain their original assumptions for reproducibility.

# PolyLab

**Current scope: Polymarket US only.** Start `start-polylab.cmd` for http://127.0.0.1:8788. The official US public collector and separate US forward-paper experiment start. No VPN or proxy is configured. International workers and replay endpoints are disabled, with prior records preserved. The dashboard shows a 24-market US display-price screen, its realized P&L graph and forward account status. No profitable US strategy has been established. See [US scope](docs/US-SCOPE.md) and [US experiment](docs/US-EXPERIMENT.md).

Current US additions are documented in [weather forecasts](docs/US-WEATHER.md), [archived MOS calibration and profit pilot](docs/US-MOS-STUDY.md), [registered Benter/Shin comparison](docs/US-BENTER-STUDY.md), and [agent comparison](docs/US-AGENT.md). The local agent comparison remains inconclusive. MOS station calibration improved temperature errors but lost $10 in the initial US price pilot; the separate ensemble probabilities still need calibration. These studies remain separate from the running paper accounts. [Feed diagnostics](docs/US-FEED-DIAGNOSTICS.md) explain why most forward books are excluded.

The current profit-validation work adds a [four-city frozen-model transfer test](docs/US-TRANSFER-STUDY.md) and a [shared-capital portfolio comparison](docs/US-PORTFOLIO-STUDY.md). US scenarios preserve $50 initial cash, $40 reserve and a $5 entry cap. No subscription cost is configured; older frozen reports retain their explicitly labeled hypothetical cost assumptions. The dashboard exposes transfer and portfolio results only when their saved accounting audits match the report hashes. The Papers page uses US study coefficients and scores; archived international results are excluded. A positive trading backtest does not establish profitable paper trading.

## Install from GitHub

From the repository directory in Windows PowerShell, with Python 3.10+ and a Node.js version supported by Vite 8 installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix web ci
npm --prefix web run build
.\start-polylab.cmd
```

The launcher starts local public-data collection and paper simulation. It does not submit real orders. Runtime databases, historical datasets, experiment registrations and ledgers, logs, credentials, and supplied full-text paper extracts are excluded from Git. A fresh clone includes the strategy catalogue and selected static research summaries, not the original local experiment archives. Historical replay commands and saved-result views require their corresponding datasets and receipts; a clone cannot reproduce missing archives from summary graphs alone.

The Benter intraday nowcast extension is work in progress: source collection and experimental modules are included, but its financial evaluation is not complete. No profit claim is made for it. The sections below labeled archived describe earlier international work, not the current US-only runtime.

## Archived international implementation

The sections below document earlier international experiments. Their workers and dashboard controls are disabled. These are not US results.

A local Polymarket research dashboard, independent paper accounts, and our own weather order-book archive. Open **http://127.0.0.1:8788**. This project is separate from SupahTrade and contains no exchange order client.

## Start and stop

Double-click `start-polylab.cmd`. It starts the loopback dashboard, four public-data paper accounts, weather books, station inputs, and a Chainlink TWAP recorder in a hidden process. If already running it reuses the existing server. Keep the computer awake and connected for recording; this is not a cloud service or a Windows startup task.

Use **Paper trading → Stop** and **Weather archive → Stop** to pause the workers independently. Existing data and simulated positions remain saved. Each paper account starts with its own $50, not a combined portfolio. Runtime logs are in `data/`; server identity is in `data/server-pid.json`.

## What works

- Interactive equity and drawdown graphs, fee/slippage controls, repeatable backtests, and CSV trade exports.
- Twelve research backtest adapters plus cash, an Avellaneda–Stoikov quote formula, and the guide's separate 15-minute forward paper account.
- Shin odds conversion, normalized implied probabilities, Benter probability combination, logistic book-feature forecasts, fractional Kelly sizing, and chronological evaluation.
- Actual Qwen3.5:9b local agent versus no agent, measured-delay agent, and a simple rule filter on identical markets. Both the original no-trade Benter comparison and the nontrivial momentum comparison are preserved.
- Weather market discovery, full-depth stream reconstruction, best-effort one-second snapshots, city-day `.jsonl.gz` downloads, order-book replay, and a strict-freshness price-only weather backtest.
- A searchable catalogue of all 297 linked strategy descriptions. **The catalogue is not 297 executable strategies.** Unimplemented entries are explicitly marked Research specification; market-making quotes are not presented as proven passive fills.
- **Strategy lab** adds 14 executable basket evaluators covering binary split/merge, gas costs, exclusive outcome baskets, strike/deadline nesting, count/temperature bands and explicit implications. Four binary variants have a separate delayed historical replay. The other evaluators require supplied settlement relationships and do not claim historical strategy returns. See [implementation status](docs/IMPLEMENTATION-STATUS.md).

The weather page is our functional version of the supplied dataset product: regions, city-day files, full levels and replay. It starts recording now. It does not claim a purchased historical dataset, complete worldwide coverage, or uninterrupted listing-to-resolution history.

## Budget

Uses the guide's conservative runnable example: $50 initial simulated capital, 10% Kelly, 15% exposure cap, 5% daily-loss entry gate, $1 minimum and $50 maximum order budget, and venue minimum shares. Historical research preserves its explicit 100 bps per-side assumption plus $0.001 per-share slippage; the historical fee schedule is unknown. Forward paper accounts now use actual Gamma `feeSchedule` metadata and the documented price-dependent taker curve, rounded to five decimals, with no rebate credit. Missing or unsupported fee metadata prevents a simulated entry. The old flat-fee accounts were stopped with zero positions and zero P&L and preserved; new accounts use `fee-v2` directories. No minimum order is forced when Kelly is smaller. A loss gate is not a guaranteed maximum loss. Monthly service cost defaults to zero for this local project and is configurable in the research engine. No paid subscription or purchase was made.

## Profit research and public inputs

The 1,200-market unused-condition study rejected the earlier positive exit-depth result: baseline −$14.82, exit-depth cap −$14.53, combined controls −$3.43. All trading variants lost money; half Kelly made zero trades. Reproducible equity figures, ledgers, receipts and paper snapshots are under `data/profit-evidence`; `latest.json` identifies the latest export. These simulations do not prove executable fills or future profitability.

- Eight risk modules and matched risk replays are implemented. Run `python -m polylab.risk_replay` for the original sample; `tools/run_profit_study.py` checks the frozen risk-code hashes before evaluating the larger registered sample.
- `data/spot` contains 132,480 one-minute BTC/USDT candles, verified against Binance's published checksums, with no minute gaps. Gaussian, logistic and Benter external-price models use only available closed candles. All three failed costed validation; `promotion-v1.json` records no approved candidate.
- Every fifteen minutes, the public-input worker saves current settlement rules, exact station metadata, METAR/TAF, Open-Meteo forecasts and US NOAA observations. Each file has its own receipt timestamp and hash. METAR is a covariate and does not replace the contractual settlement source.
- The Chainlink relay worker records 30- and 60-second BTC/USD TWAPs, with observation, publisher and local receipt timestamps. Bootstrap frames remain available only at their receipt time. Gaps and reconnects are logged; no invented historical availability is inserted.
- `GET /api/public-inputs` reports both collectors. The Weather archive start/stop controls also control these inputs. Each new input archive has a 500 MB cap. No paid APIs are used.
- Full GFS, ECMWF and ICON member forecasts now feed automatic temperature probability scans. The backend includes local-day/DST handling, station calibration fitting, observed-extreme conditioning and fee-aware candidate evaluation. These are partial weather components awaiting real calibration and forecast-profit replay. See [weather probability implementation](docs/WEATHER-PROBABILITY.md).

## Reproduce

From this directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m polylab.research
.\.venv\Scripts\python.exe -m polylab.coherence_replay
.\.venv\Scripts\python.exe -m polylab.agent --strategy momentum-trend-following
.\.venv\Scripts\python.exe tools/validate_release.py
npm --prefix web run build
```

The model comparison requires local Ollama and `qwen3.5:9b`. No cloud API key is used. The API provides only a loopback public-data simulator. Research runs get unique directories under `data/runs`; datasets are frozen by SHA-256 under `data/datasets`. The latest run pointer changes without overwriting earlier reports.

For a clean installation, create a Python 3.10+ virtual environment, install `requirements.txt`, run `npm --prefix web ci`, and build the frontend. Re-download sources with `tools/download_history.py`, prepare with `tools/prepare_history.py`, and collect the catalogue with `tools/collect_catalog.py`. These use bounded public requests; no wallet is required.

Read [results](docs/RESULTS.md), [methodology and limits](docs/METHODOLOGY.md), [QA evidence](docs/QA.md), and [design notes](docs/DESIGN.md).

Latest allocation research: [US-ALLOCATION-RESEARCH.md](docs/US-ALLOCATION-RESEARCH.md). Five cities, common decision time, expected-dollar vs equal-budget comparison. Both lost money; audited results and graphs are visible in the US dashboard. No subscription cost is configured.
