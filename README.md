# Stock Explorer

A lightweight Streamlit stock-analysis app for company search, daily historical prices, indicators, percentage-return comparisons, and optional experimental forecasting. It runs in one CPU process with no LLM calls, required database, new dependency, or separate model server.

## Run and deployment

```bash
python -m pip install -r requirements.txt
python -m streamlit run dashboard/app.py
```

Use Python 3.11+ and `dashboard/app.py` as the Streamlit Community Cloud entry point.

## Search and profiles

The company dropdown searches 20 saved names and tickers in `data/companies.json` without a company API call. Under **Ticker not listed?**, the user explicitly submits a ticker. The app validates its format and requests daily history before adding it to a bounded session-only list of up to 10 additional symbols. A missing response is not reported as proof that a ticker is invalid; rate limits and provider outages can produce the same symptom.

Company overviews are optional. **Load company overview** requests a profile only when clicked. Successful results are shared in a bounded one-day memory cache and at most 10 profile entries are retained per user session. API failures do not prevent price analysis. Browsing never writes profiles into GitHub or Neon. The starter JSON contains names, with overview fields pending until a successful offline API refresh is committed:

```bash
python scripts/refresh_companies.py --symbols AAPL MSFT
```

Review and commit successful updates. Failed or incomplete refreshes preserve previous saved profiles. Provider rate limits can prevent a refresh.

## Resource controls

- History is downloaded once per ticker for two years, reused for shorter chart periods and forecasts. Five years is fetched only when requested.
- Prices use a shared four-hour memory cache capped at 48 entries. Profiles use a one-day cache capped at 48 entries; forecasts use a one-day cache capped at 24 entries.
- Daily downloads request adjusted bars with a 12-second provider timeout. Invalid/nonfinite rows are removed and exchange session dates are normalized without shifting them to a different calendar date.
- A shared nonblocking network semaphore limits concurrent provider calls. Other cold requests receive a short retry message; same-key requests benefit from Streamlit's shared cache.
- Forecast computation is button-driven, uses one CPU worker, and has a shared nonblocking semaphore allowing one computation at a time per app process. Scikit-learn is imported lazily on the forecast path.
- Additional ticker and comparison requests have 20-second per-session cooldowns; company-profile requests have a 60-second cooldown. These are convenience resource controls, not a comprehensive abuse-prevention system.
- The view selector executes only the selected view, avoiding eager rendering of hidden Streamlit tabs and unnecessary chart generation. Comparisons request another ticker only after the user clicks Compare stocks.
- Caches and custom symbols disappear on app restart. Successful cache entries are not refreshed in the background. Expired entries require a new download; this app does not promise stale-data availability during provider failures.

These changes reduce repeated work. They do not establish a tested capacity of 100 concurrent users or guarantee a free-provider quota. Distinct cold symbols, overlapping visits, model requests, and provider availability determine capacity. No paid service is introduced by the app.

## Analysis and forecast

The app shows period return, daily return standard deviation as volatility, and maximum drawdown from earlier highs within the selected period. Factual summaries are computed directly from prices. Comparisons align shared session dates and start both series at 0% on the first shared date. Charts can switch between line and candlestick; moving averages are optional. RSI/MACD/volume have a separate view.

The model predicts an endpoint return over 1–30 trading sessions, using past returns, moving-average distance, volatility, and relative volume. An 80-tree regularized Random Forest competes against unchanged price in three expanding chronological development folds. A horizon-sized gap prevents training labels from reaching test origins. Method selection uses development folds; a separate latest holdout reports return MAE in percentage points. The selected method is refit on known labels and predicts from the latest unlabelled row. If unchanged price wins validation, no unnecessary extra model fit is run for the holdout.

At least 250 usable labelled rows are required. Overlapping multi-session test targets are correlated. No future accuracy improvement, confidence probability, synthetic daily path, trading profit, or investment recommendation is claimed. Daily bars may include an unfinished session, be delayed, and be adjusted for corporate actions. Download time and latest bar date are shown separately. When profile currency is unavailable the UI explicitly labels quote units instead of assuming USD.

## Database behavior

Normal browsing makes no Neon connection or database write. CSV download is available locally in the user browser. Existing database rows are not automatically deleted, and no cleanup or retention migration is performed by this change.

Optional administrator export is shown only with `ENABLE_DATABASE_EXPORT=1`; existing `DATABASE_URL`/Streamlit secrets configuration is handled by `etl/load.py`. Export explicitly replaces a deterministic table named `prices_<symbol hash>` and persists until removed or replaced. Old ticker-named export tables are not deleted. Enable export only when persistent storage is wanted.

## Free-host sleep and best-effort wake-up

Streamlit Community Cloud's documented policy puts apps to sleep after 12 hours without traffic. Any viewer can click the platform's **Yes, get this app back up!** button. Code inside a sleeping app cannot wake its stopped process.

A separately configured ChatGPT scheduled browser check visits the public dashboard every eight hours and clicks that visible wake button if needed. It performs no forecast, comparison, profile request, database export, or repository modification, and reports verification failures. The scheduled check is best effort: browser access, task availability, startup delays, and hosting policy can affect it. It does not disable Streamlit hibernation or guarantee always-on hosting. The app uses no in-process keep-alive loop, empty commits, or HTTP-only claim of a verified app session.

## Validation

```bash
python -m pip install pytest
python -m pytest -q
```

Tests use mocked data and do not require a running database or live Yahoo requests. They cover chronological purge boundaries, latest-row inference, baseline fallback, local catalog search and refresh failures, safe symbol handling, price cleaning, shared mutation-safe caches, semaphore contention/release, calculation/alignment correctness, button-only API/model execution, custom ticker flow, and optional database behavior. Legacy database tests are aligned with the deployed loader's connection-check behavior rather than the old local database-creation implementation.
