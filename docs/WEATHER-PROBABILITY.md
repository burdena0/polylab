# Weather probability implementation

The temperature portion of the requested ensemble strategies now has executable probability components and an automatic public-data pipeline. This is not a demonstrated profitable weather strategy.

The collector saves every member of GFS (31), ECMWF IFS (51), and ICON Global (40). The first complete archive has eighteen files covering six station locations, with URL, requested and returned coordinates, member count, receipt time and SHA-256 for each file. A subsequent version includes the prior UTC day, needed to cover the beginning of the current local day in Europe. The old incomplete-window archive and rejected model run remain preserved.

Each member's daily maximum or minimum is calculated over the station's local calendar day before counting its temperature bucket. This differs from taking the daily maximum of the ensemble mean. DST days can have 23 or 25 hours. A missing hour/member, unknown unit, duplicate time, future receipt or non-exhaustive ladder rejects the calculation. Coarser native model timesteps are interpolated by the API; this is not an exact reconstruction of every station reading.

`weather_probability.py` provides NOAA rule and integer-band parsers; full-member daily extremes; unit conversion; exhaustive-band frequency estimates; observed-extreme conditioning; station/model-specific bias and spread fitting; and fresh-quote candidate scans with actual Gamma fees, slippage, Kelly budgets, depth and venue minimums. Calibration requires at least twenty distinct previously resolved station days. No real station calibration has yet been fitted or validated. Expected P&L is a conditional model estimate, never realized profit. No weather candidate is promoted into a paper account by this component.

The actual NOAA viewer source was inspected and hashed. It uses `Math.round` for the temperature table and station-local time. The ASOS/AWOS hourly branch requires a non-null sea-level-pressure observation and can include METAR/SPECI reports; it is not a filter for minute zero. Reviewed evidence expires after 24 hours and fails on a changed file hash. NOAA station metadata confirms timezones for LaGuardia and Dallas Love Field; other station conventions remain unverified against the resolution source. No embedded API credential was retrieved or used.

The first complete-window run evaluated twenty-one model/market combinations across seven temperature markets. Hong Kong was rejected because its Observatory source and decimal precision require a different adapter. Active-market coverage changes on subsequent runs; reports are preserved independently.

## Runtime

The weather start/stop controls also manage these inputs. Station inputs refresh every fifteen minutes; ensembles at most hourly. A model scan runs after each collection and reads currently fresh complete YES/NO pairs from the book recorder. Empty or stale books do not become fills. Each ensemble archive has a 500 MB cap; each collection has a four-minute budget. Timeouts are recorded and retried on the next collection.

- `GET /api/weather/models`: latest immutable probability report.
- `POST /api/weather/models/run`: save a new live-input scan.
- `POST /api/weather/probability`: evaluate timestamped members, rule, bands, calibration and optional observations.
- `POST /api/weather/bias-fit`: fit a supplied resolved station calibration dataset.
- `GET /api/public-inputs`: collector status, source directories and model counts.

Remaining work includes out-of-sample station calibration, exact matching of contractual observations, other settlement sources and precision conventions, hurricane/snowfall models, and profit backtests using genuine forecast vintages and executable book evidence. Collecting today's forecast with past hours does not create historically available predictions.

Sources: [Open-Meteo ensemble API](https://open-meteo.com/en/docs/ensemble-api), [NOAA viewer source](https://www.weather.gov/source/wrh/timeseries/obs.js?v202601121730), [requested ensemble strategy](https://www.polyresearchrobotics.com/strategies/ensemble-spread-probability-trading), [requested weather strategy](https://www.polyresearchrobotics.com/strategies/weather-event-markets).
