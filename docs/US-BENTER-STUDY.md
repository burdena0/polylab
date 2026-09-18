> Cost correction (September 17): No paid model/data subscription is configured for PolyLab. The inherited $200/month is a legacy hypothetical sensitivity, not an actual bill. Current profit excludes this deduction; fees and slippage remain. Frozen historical artifacts retain their original assumptions for reproducibility.

# US forecast and market probability study

This is an exploratory Polymarket US adaptation of the user-supplied Benter and probability-from-odds papers. It follows the losing six-date weather pilot and does not overwrite it. Only public US data is collected; no VPN, account creation, paid services or orders are involved.

## Registered design

The immutable study directory is `data/us-benter/1789690917159502000`. `protocol.json` precedes event discovery, and `registration.json` precedes price and settlement downloads. The registration selected all available KNYC event dates in fixed windows: July 28–August 16 for MOS bias/spread training, August 17–31 for combination fitting, and September 8–16 for profit evaluation. The earlier September 1–7 pilot is excluded. August 28 was absent from the bounded official event response, leaving 14 calibration and nine test dates. No replacement dates are selected after inspecting coverage or returns.

The earlier MOS archive supplies GFS/NAM forecasts and original complete CLI observations. Its previously fitted coefficients are discarded; new station coefficients use only the registered 20 training dates. Forecast availability remains an assumption of nominal runtime plus six hours. A forecast is excluded when the fitted station model was not yet available at the decision time. These dates' temperature errors were summarized in earlier research, so this is a new price test within an exploratory research sequence, not a pristine independent study.

The Benter adaptation fits probabilities proportional to `forecast^alpha * market^beta`. The objective is mean multiclass negative log likelihood plus a predeclared 0.01 squared-distance penalty from market-only weights `(0,1)`. Weights are bounded to `[0,4]` and probability inputs floored to 0.000001 before normalization. At least 10 eligible distinct calibration dates are required. This regularization is a study adaptation, not a formula claimed from Benter. There is no P&L-based coefficient or threshold tuning.

Model-only, fixed equal-weight log-probability blend, fitted Benter, market-only, and Shin-derived exchange-ask probabilities share the same test account rules. Shin rejects underround ladders; exchange asks do not establish bookmaker insider assumptions. Complete contemporaneous six-contract ladders are required. Calibration labels require exact, mutually exclusive unit settlement payouts. Fitting uses assumed next-day 11 AM ET settlement availability plus a 24-hour embargo; actual historical exchange publication timestamps are not supplied.

## Profit and accounting

Each independent scenario starts with $50, preserves $40 cash, and spends at most $5 per entry. Decisions occur six hours before the fixed-standard-time NYC climate day; entry uses a quote at least 60 seconds later with a 300-second maximum wait. The selected contract cannot switch based on future prices. Expected dollar edge must remain at least $0.10 after fees and portfolio sizing. Cash stays locked in overlapping positions until the separately disclosed assumed settlement time. Quantities are whole contracts; historical displayed depth and actual fills are unverified.

The September 17 US fee curve is applied to earlier dates as a counterfactual. Added slippage scenarios are zero and half a cent per side. A $200/month subscription is allocated over the same test window to each scenario, separately from the trading reserve. The graph and table report realized trading P&L, external overhead and open basis; probability scores are descriptive and do not establish profit. Unavailable fitted models must be labeled unavailable rather than treated as successful zero-trade strategies.

## Reproduction

1. Register a new study with `tools/register_us_benter.py`; never overwrite an old registration.
2. Collect or resume the same directory with `tools/collect_us_weather_history.py DIRECTORY`. Each invocation is bounded and honors the shared US cooldown.
3. Finish all registered requests before `tools/run_us_benter.py DIRECTORY`. A new analysis directory records coefficients before evaluating test P&L, full ledgers, source/code hashes and `benter-profit.png`.
4. Run `tools/audit_us_benter.py ANALYSIS_DIRECTORY` for independent Decimal ledger, fee, reserve, settlement, expense and log-loss reconciliation. Preserve all prior analyses.

## Completed result

The collection completed all 276 responses without request errors: 10,942 usable price records, including 3,499 on test dates, and 138 verified contract payouts. Ten of the 14 registered calibration dates were eligible. August 17 was excluded because the fitted forecast model was not yet available; three further dates lacked complete contemporaneous ladders. Eight of nine test dates had complete signals; September 16 did not.

The immutable output is `data/us-benter/1789690917159502000/analysis-1789692289582301300`. `audit.json` independently reconciles the inputs, fees, account ledgers, payout sides, reserve, subscription and log-loss scores. All positions closed.

| Method | Trades, no extra slip | Trading P&L | Trading P&L with half-cent slip | After overhead, no extra slip |
| --- | ---: | ---: | ---: | ---: |
| MOS only | 5 | -$9.96 | -$9.95 | -$74.40 |
| Fixed blend | 5 | -$9.99 | -$9.98 | -$74.43 |
| Fitted Benter | 7 | +$17.25 | +$16.70 (6 trades) | -$47.19 |
| Market only | 1 | -$4.97 | $0.00 (0 trades) | -$69.41 |
| Shin asks | 0 | $0.00 | $0.00 | -$64.44 |

The fitted weights were alpha=0.00601 and beta=1.37381. This gave almost no weight to the independent forecast and sharpened market probabilities. The promising hypothesis is market probability recalibration, not a newly demonstrated weather-information advantage. The three largest profitable trades contributed 89.1% of Benter's trading gain. This small, concentrated result is a research lead, not durable or fill-verified profitability. The allocated subscription still exceeds the gain.

Next: register additional untouched US contracts and forward observations to test the same frozen weights and a disclosed market-only calibration ablation. Preserve this result, do not optimize on these dates, and verify quote depth before treating hypothetical fills as deployable. The separate basket test found no qualifying structural inefficiency in its sampled windows.

Additional cost-capacity diagnostics are saved beside the audited report as `edge-diagnostics.json` and `edge-diagnostics.md`. In the zero-added-slip Benter arm, entry-time model probabilities implied only $1.75 of summed expected edge, compared with the scenario's $17.25 realized gain. This gap is not proof of miscalibration by itself, but it makes the small-sample profit unsuitable as a forecast of earnings. The estimated edge was about $0.18 per registered day, versus $6.67 per day of allocated subscription. These model expectations are unvalidated and assume the historical display-price fills. Four-city transfer and a separately registered shared-$50 allocation test now investigate the lead without changing the NYC trades.

Sources: user-supplied Benter paper, retained as `docs/benter.txt` (second-stage probability model); [official US event API](https://docs.polymarket.us/api-reference/events/get-events), [US historical prices](https://docs.polymarket.us/api-reference/price-history/get-price-history), [US fees](https://docs.polymarket.us/fees), and [IEM MOS archive](https://mesonet.agron.iastate.edu/mos/fe.phtml).
