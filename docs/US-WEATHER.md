# US weather forecast component

The first US archive is `data/us-weather/1789688788485319700`. It contains 60 actual temperature contracts, 15 CLI products and 15 full ensemble responses, yielding 30 station/date/model distributions across New York, Miami, Chicago Midway, Los Angeles and San Francisco. Forecast systems are GFS (31 members), ECMWF (51) and ICON (40). Each member retains its own full-day maximum before probability counting; models are not pooled as independent samples.

## Settlement identity and time

The adapter reads each US contract's full description. It uses Central Park KNYC, KMIA, KMDW, KLAX and KSFO with their corresponding NWS CLI products. The slug is not the rule: for example, the NYC slug ending `gte80lt81f` has prose specifying between 80F and 81F. The adapter follows the inclusive integer prose bounds and verifies complete, gap-free partitions.

CLI climate days run midnight-to-midnight local standard time, including during daylight saving time. The implementation uses fixed offsets of UTC-5, UTC-6 or UTC-8 and exactly 24 forecast hours. Spring and autumn DST boundary tests prevent substituting a 23/25-hour civil day.

The parser verifies product code, CLI station, climate-summary date and issuance before receipt. It reads only the observed temperature table, not record temperatures or tomorrow's normals. Missing values are rejected. An afternoon TODAY/AS OF report is interim. A complete-day report is still revisable and is not marked as exchange-settled. The September 17 NYC afternoon report recorded 82F; it is retained as a provisional observation, not final settlement.

## Forecast and quote limits

Forecasts carry source URLs, receipt-time availability, content hashes, station coordinates and raw member series. Collection after the day's start is not a historical forecast from before the day. Probabilities use an explicit nearest-degree quantization assumption; station bias, continuous-observation extremes and spread calibration remain unverified. Conditioning on an integer CLI high clips the integer model outcome, not an invented exact Celsius observation.

The costed scanner uses the minimum Yes probability across models for a long, or one minus the maximum for a short, with US fees, whole simulated lots, a $5 budget and 25% top-depth cap. These are model sensitivity estimates, not statistical confidence bounds. No weather position or real order is created.

The first quote pass found one-sided books, then stopped on HTTP 429. It produced zero eligible quote comparisons. This is incomplete coverage, not evidence that no weather opportunities exist. The common US transport now coordinates request pacing and shared cooldown across processes, including the separate forward-paper experiment.

For September 18, mean forecast highs differ materially: KNYC roughly 80.6–83.7F, KLAX 75.1–81.0F and KSFO 70.0–77.0F. Such disagreement makes calibration necessary; it is not profit evidence. The next step is matching archived pre-day forecasts to subsequently published complete CLI observations and actual US settlement receipts, then evaluating on untouched days.

Run `.venv\Scripts\python.exe tools/collect_us_weather.py` for a new bounded archive after any shared cooldown. It stops within its collection budget and preserves partial results. It is not a one-second full-book recorder.

## Primary sources

- [Polymarket US weather settlement](https://docs.polymarket.us/faqs/weather-faqs)
- [NWS observation and climate FAQ](https://www.weather.gov/lot/weather_observations_faq)
- [NWS climate product specification 10-1004](https://www.weather.gov/media/directives/010_pdfs/pd01010004curr.pdf)
- [NWS NYC CLI index](https://api.weather.gov/products/types/CLI/locations/NYC)
- [Open-Meteo ensemble documentation](https://open-meteo.com/en/docs/ensemble-api)
