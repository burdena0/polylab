# Polymarket US scope

User restriction effective September 17, 2026: use the US venue so no VPN is required. This is not merely a US-city filter on the international exchange.

Only US workers start: the public collector and a separate local forward-paper experiment. Requests use the official gateway and an allowlist of listing, book, history and settlement GET paths. Redirects and environment proxies are disabled. International paper/weather/oracle workers are stopped; start controls and replay endpoints are blocked. Prior evidence remains archived. Dashboard navigation shows US markets, US screening/forward results, an initial adaptation shortlist and research papers. Daily automation follows this restriction.

Discovery has observed sports, politics, culture, finance, technology, macro, geopolitics and crypto. Bounded batches advance a persisted pagination cursor and preserve raw responses. This is partial discovery, not historical fill evidence or a complete point-in-time census.

The whole-contract help page conflicts with observed fractional depth and minimumTradeQty metadata. Raw quantities are preserved; normalized books are not real-execution eligible. The separate paper experiment explicitly simulates whole contracts. Fee documentation effective September 17 gives taker theta 0.0695 and maker rebate theta -0.0125 in theta * contracts * p * (1-p). Fees round half-even to cents, with a cumulative cap on aggressive matching fills. The simulator uses the rounded aggregate exact fee as an upper bound because book depth does not reveal matching fragmentation. No maker rebates are credited.

US weather uses NWS Daily Climate Reports, including KNYC Central Park for NYC. Earlier international LaGuardia and hourly-viewer rules cannot be reused.

A 24-market US price-based feasibility replay and realized P&L graph are implemented. Momentum and mean reversion lost money in this sample. A separate US forward-paper experiment is running; its first snapshot showed zero entries, not profit. See US-EXPERIMENT.md for evidence and limits. International returns are not US performance. Broader strategies, independent validation and US agent comparisons remain unfinished.

## Official sources

- [Public API](https://docs.polymarket.us/api-reference/introduction)
- [Market books](https://docs.polymarket.us/api-reference/markets/get-market-book)
- [Rate limits](https://docs.polymarket.us/api-reference/rate-limits)
- [Whole-contract help](https://docs.polymarket.us/learn/trading/basics/fractional-shares)
- [Fees](https://docs.polymarket.us/fees)
- [Weather settlement](https://docs.polymarket.us/faqs/weather-faqs)
