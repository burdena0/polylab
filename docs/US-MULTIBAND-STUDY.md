# Multiple-band allocation and prospective quote-paper comparison

September 17, 2026 local New York. Objective: maximize net dollars with a shared $50 account, $40 cash reserve, $5 aggregate city cap and no subscription charge. A fresh experiment must not overwrite earlier losing runs.

## Historical comparison

Registration: `data/us-multiband/1789698808777485000/registration.json`.
Analysis: `analysis-1789698832198014000/report.json` and `audit.json` within that directory.

The new two-stage dynamic program permits several distinct temperature instruments per city, but at most one side/quantity choice for each instrument. It builds each city's cost/expected-profit frontier and then allocates the shared cash across cities. Fees, upward cent rounding for reserved allocation, whole quantities, minimum $0.10 modeled edge per leg and the $5 city limit apply throughout. It enumerates mutually exclusive event payoffs rather than assuming bands win independently. Signal choices are frozen before delayed entry quotes; neither replacement trades nor future settlement cash are allowed.

This changes allocation only. It retains the prior normalized market-probability exponent 1.3738073703598581, which has already lost money in cost-stressed tests. There is no forecast refit or new information edge. September 8–16 outcomes were already examined, so this is a retrospective comparison, not independent validation.

| Method | Added slippage | Net simulated PNL | Entries | Open basis |
|---|---:|---:|---:|---:|
| Single band | $0 | -$9.32 | 9 | $0 |
| Multiple bands | $0 | -$9.32 | 9 | $0 |
| Single band | $0.005 | -$9.53 | 9 | $0 |
| Multiple bands | $0.005 | -$9.53 | 9 | $0 |

Thirty-nine of 45 city-date ladders were complete. The multi-band optimizer selected no multi-leg city bundles in this sample: the best feasible choices were unchanged. The single-band control reproduces the original allocator's full ledger exactly in both cost arms. An independent SciPy integer solver matches all 18 multi-band decision objectives. Together with Decimal fee, cash and payout reconstruction, the audit passed 312 checks. This validates calculations, not historical depth or fills.

Implementation: `polylab/us_multiband.py`, `polylab/us_multiband_replay.py`, `tools/run_us_multiband.py`. The source and registration are frozen. Reproduction: `.venv/Scripts/python.exe tools/run_us_multiband.py data/us-multiband/1789698808777485000` creates a new analysis; do not edit the original.

`tools/render_us_multiband.py` renders the audited results with one cumulative value per exact timestamp. This avoids misleading zero-duration spikes from sequential accounting of settlements sharing a timestamp. The earlier plot is preserved; use the later `render-*` output and its exact source rows.

## New prospective experiment

Registration: `data/us-multiband-forward/1789699215223439000/registration.json`.
Worker: `tools/collect_us_multiband_forward.py`, with helper `polylab/us_multiband_forward.py`.

Thirty frozen September 18 high-temperature contracts span KNYC, KMDW, KMIA, KLAX and KSFO. Fixed city order is registered, and a missing or invalid quote rejects the whole city's signal ladder. Each alternative has one independent $50 account shared across cities; their profits cannot be summed.

- Signal collection: September 18 03:55–04:00 UTC, or September 17 11:55 PM–September 18 midnight Eastern.
- Decision: September 18 04:00 UTC. The worker must record it within 30 seconds; missed decisions are not reconstructed later.
- Entry: quotes requested no earlier than 04:01 UTC and received by 04:05 UTC. Choice and maximum quantity/budget remain fixed. Actual observed top depth limits each simulated fill to 25%, after whole-contract rounding; fees and half-cent slippage apply.
- Settlement collection: no earlier than September 19 15:00 UTC / 11 AM Eastern, using actual receipt time for cash release. Missing payouts remain unresolved positions.
- Stop: September 19 16:00 UTC / noon Eastern. The experiment is not silently extended.

The signal HTTP-age bound is 300 seconds; the entry bound is 45 seconds. Both require an explicit Age header. Exchange transactTime must exist and not lie in the future, but its age does not impose the older five-second gate: the public REST documentation did not establish that this field measures book generation time. This is an explicit new protocol and an execution sensitivity, not evidence of true fills or permission to relabel older rejected quotes as trades. Older experiments and their gates remain immutable.

The worker uses only the existing allowlisted public US GET client and shared rate limiter. It records signal books, an immutable decision plan, delayed books, entry results and later settlement receipts. It serializes processes and fails closed on interrupted capture phases, rather than replaying old opportunities. No account creation, authentication, order API, paid model or hosting service is used.

The successful worker was verified live as PID 43140 (venv launcher PID 47992), exec session 76197, waiting for its future signal window. A prior launch used a nonexistent directory and exited before opening any files; that handle is terminal and must not be resumed. Read the active pointer and verify the successful process before considering a restart.

All 170 tests pass, including exhaustive small-portfolio optimization, mutually exclusive payoffs, unchanged decisions under altered future data, depth caps, fee/reserve accounting, missing payouts, identity/HTTP-age checks, and a synthetic full collector lifecycle including interrupted capture. Synthetic lifecycle test profits are fixtures, not trading results.

This prospective decision has no result yet. One decision cannot establish repeatable profitability. Continue the existing CLI and paired weather-feed studies in parallel, and prioritize a better calibrated information source over repeatedly changing allocation on the losing market-only model.

The previous goal turn was progress: it corrected station-feed handling, collected public-account evidence and completed the endgame screen. This turn also changes authoritative state and adds a registered live future experiment. The overall goal and the greater-than-$5 net target remain incomplete.
