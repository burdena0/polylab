# Release validation

Executed 17 September 2026 on Windows.

- Python unit suite: **28 passed**. Covers paper odds examples, Benter combination, correct Kelly payoff/minimum handling, causal features, delayed fills, depth/minimum-share constraints, agent vetoes, locked unexited capital, timestamp precision, and weather stream initialization/update/disconnect validation.
- Production Vite build passed. Bundler reports a large initial chunk and harmless ignored dependency `use client` directives; no build failure.
- Browser testing used bundled Playwright with installed Chrome in headless mode. The specific Browser plugin was unavailable; the bundled default Chromium executable was absent, so installed Chrome was used.
- Checked desktop 1536×1024 and mobile 390×844. No browser page errors; mobile document width equals viewport width. Wide data tables scroll within their own containers.
- Exercised strategy search, detail modal, Shin calculator, agent comparison, weather replay slider, CSV trade export and backtest rerun. Downloaded CSV contents matched the report ledger. Weather gzip download was decompressed and every returned row parsed.
- Live checks confirmed connected weather capture and running primary/guide paper workers. Fixed Coinbase nanosecond timestamps for Python 3.10; direct feed and subsequent paper decision both succeeded. The failed paper state was backed up before retrying the data observation.
- Weather backtest rejected the selected file for insufficient fresh decision observations. This limitation is displayed instead of a fabricated successful result.

Visual comparison against `concept.png`: retained the dark navigation rail, white panels, teal primary actions, four-column budget strip, and chart/library hierarchy. Intentional additions are separate papers, agent, paper-account and weather-archive pages. The supplied weather reference inspired region cards and city-day downloads, adapted to a working local archive rather than a storefront.

Screenshots are in `docs/screenshots/`. Current automated data/cost receipts are in `data/release-validation.json`. Network availability, full-day collection, prospective returns and all 297 strategy implementations remain outside what these checks establish.
