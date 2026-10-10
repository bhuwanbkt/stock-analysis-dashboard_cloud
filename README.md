# Stock Explorer

A lightweight Streamlit dashboard for company search, historical prices, indicators, stock comparisons, and experimental forecasts. Optional Neon PostgreSQL storage shares data across visitors and survives app restarts. The app uses one CPU process, no LLM calls, and no separate model server.

## Run

```bash
python -m pip install -r requirements.txt
python -m streamlit run dashboard/app.py
```

Use Python 3.11+ and `dashboard/app.py` as the Streamlit Community Cloud entry point.

## What happens when someone opens the app

1. The dropdown combines the starter names in `data/companies.json`, saved database companies, and up to ten additional listings in the current session. Searching this dropdown makes no company-search API call.
2. The selected stock first uses the shared four-hour memory cache. On a cache miss, the app checks Postgres when configured.
3. Saved two-year prices downloaded less than 24 hours ago are reused without a provider download. Missing or older prices trigger a download for **that selected stock only**. There is no daily job downloading every saved company.
4. Valid prices are upserted by ticker and session date, rather than appended repeatedly. Concurrent database requests coordinate through a three-minute refresh lease with a unique token. A completed refresh from an expired worker cannot overwrite a newer worker's results. Failed downloads release the lease and wait five minutes before another database-coordinated attempt.
5. If the provider fails, existing saved prices remain visible with a warning and the last download time. If no saved prices exist, the app shows a retry message. A provider outage is not proof that a ticker is invalid.

The URL stores the selected ticker, for example `?symbol=SONY`. After sleep or restart, that link restores the selection. A plain link defaults to AAPL. Other session choices and memory caches reset; database records remain. Opening a shared link for an uncached ticker can initiate its normal price download.

Freshness refers to **download age**, not a guarantee of the latest market close. Memory caching can delay the next freshness check by up to four hours. Daily data may be delayed or include an unfinished session. Download time and latest bar date are displayed separately. A stale-data warning provides a manual retry button; the database retry delay still applies.

## Bounded shared storage

Add the following top-level Streamlit secret, or environment setting, to enable persistence:

```toml
DATABASE_URL = "your Neon PostgreSQL connection URL"
```

Use the existing database role with permission to create and read/write the app's tables. Keep credentials out of GitHub. On first successful connection, the app creates these additive tables:

| Table | Purpose | Limit or retention |
| --- | --- | --- |
| `stock_companies` | Company names and JSON-encoded profiles | At most 50 saved companies |
| `stock_daily_prices` | Adjusted daily OHLCV, unique `(symbol, Date)` | Rolling two calendar years; at most 600 rows per company |
| `stock_refresh_status` | Last download, lease token, retry state | Saved companies plus bounded transient failed lookups; expired transient rows removed on refresh claims |
| `stock_forecast_runs` | Forecast result and later observed return | 90 days; hard maximum 5,000 records |
| `stock_maintenance` | Capacity coordination and weekly cleanup timestamp | Two coordination rows |

Typical equity history is around 500 daily rows per company, or around 25,000 price rows across 50 companies. The hard price cap is 30,000 rows. Exact storage bytes include profiles, forecasts, indexes, and PostgreSQL overhead; these are row bounds, not a promised database size or provider quota. Existing export tables count toward your Neon usage separately.

At the company limit, new stocks can still be viewed in memory but are not saved, and the UI explains this. The app does not automatically evict saved companies. Unknown tickers with failed history downloads do not become saved companies. Five-year chart history remains in memory and does not expand the saved two-year window. Forecasts always use at most the latest two years of the supplied history.

A refresh downloads the complete two-year provider window, rather than only the latest day. This is a deliberate tradeoff: corporate actions can revise previously adjusted prices, so successful refreshes replace values for matching dates and remove dates absent from the current snapshot. Invalid or incomplete responses are not persisted. CSV download is available for the selected chart period.

Connections use `NullPool`, closing client connections after each transaction instead of holding an idle connection open. Database errors fall back to API/memory when possible; fallback data is explicitly labelled and is not guaranteed to survive a restart. A database outage can increase provider calls after cache expiration. Refresh leases coordinate only when shared storage is available; the network and model semaphores apply per app process.

## Cleanup and sleeping apps

Automatic cleanup checks a **database-persisted timestamp**. When seven days have elapsed since the last successful cleanup, an active visit removes prices outside the two-year window and forecast records older than 90 days. Deletes and the timestamp update commit together; a failed cleanup rolls back and does not advance the timestamp. An hourly memory gate avoids checking maintenance on every rerun; a restarted process checks again. A successful price refresh also prunes that ticker immediately.

A sleeping app performs **no downloads, model work, or cleanup**. Its next active visit checks whether cleanup is due and checks prices for the selected stock. Fresh saved data needs no download; stale or missing selected-stock data is downloaded automatically when available. There is no background scheduler inside this app, no polling loop, and no attempt to keep Neon permanently awake. Retention is enforced when the app is active, so unused records can remain past their cutoff during sleep.

These managed tables are separate from previous ticker-named, `stocks`, and `prices_<hash>` export tables. Old exports are not imported or automatically removed. The dashboard no longer exposes the old replace-table export action. Automatic maintenance only deletes rows in `stock_daily_prices` and `stock_forecast_runs`.

### Manual removal of old and new prices

Click **Open admin page** at the top of the stock dashboard's sidebar, above **Chart period**, to open the separate **Database administration** page at `/admin`. Price charts and company search stay on the main page. Use **Back to Stock Explorer** to return; the selected ticker is preserved within the same session. Opening the admin page does not request market data, run forecasts, or automatically delete anything.

The admin controls are locked unless both `DATABASE_URL` and a private `DATABASE_ADMIN_TOKEN` of at least 24 characters are configured:

```toml
DATABASE_ADMIN_TOKEN = "a strong unique administrator password of at least 24 characters"
```

#### One-time administrator setup

`DATABASE_ADMIN_TOKEN` is a private password you create yourself; it is not issued by Neon or Streamlit and is separate from your database password. On macOS, open Terminal and generate it with:

```bash
openssl rand -hex 32
```

This prints a random 64-character value. Save it in your password manager, then add it as the value of `DATABASE_ADMIN_TOKEN` in **Streamlit Cloud → your app → Settings → Secrets**, and click **Save**. Keep the existing `DATABASE_URL` if it is already configured. Do not paste either secret into chat, screenshots, or GitHub.

This setup is one-time: Streamlit retains the secrets across app sleep and restart. The administrator password is only needed for manual cleanup; automatic shared storage and weekly retention use `DATABASE_URL`. If the administrator token is missing, manual cleanup stays locked.

#### Open the admin page and delete selected prices

1. Click **Open admin page** at the top of the sidebar, or open [Database administration](https://stock-analysis-dashboardcloud-ga4trnosdubt58eqgynqtk.streamlit.app/admin) directly.
2. Enter the generated token value in **Database administrator password**, then click **Unlock database cleanup**.
3. Click **Refresh saved price tables** to list eligible tables.
4. Select **Saved price tables** and choose **Rows before a date** or **All rows (old and new)**. For date-based deletion, rows on the selected cutoff date are kept.
5. Type `DELETE` in **Type DELETE to confirm**, tick the permanent-deletion confirmation, and click **Delete selected saved rows**.
6. Check the reported deletion counts. Use **Lock database cleanup** to end administrator access, or **Back to Stock Explorer** to return to the dashboard.

Unlocking expires after 15 minutes; enter the same password again afterward. Closing or restarting the app can also end the session. Changing the configured password invalidates existing administrator access. There is no need to generate a new password each time.

The stock dashboard and administrator page use explicit Streamlit page registration, so the navigation works when an already running app receives an update. The administrator page contains the login and cleanup controls; company search and charts stay on the dashboard.

Eligible tables must have Date/Open/High/Low/Close/Volume columns and be `stock_daily_prices`, a known legacy ticker table, `stocks`, or a `prices_<12-character hash>` export. Other exact legacy names can be configured in `DATABASE_LEGACY_STOCK_TABLES` as a comma-separated list. Unrelated tables are excluded. The backend rechecks scope, quotes identifiers, binds dates, locks selected tables briefly, and blocks incoming foreign keys or custom triggers. It keeps table structures and rolls back the transaction on failure.

Manual cleanup does not remove company profiles, forecast records, or existing memory cache entries. Removing saved prices is not a permanent suppression of future downloads: the next uncached request can download and save them again. Download a backup before deleting records you need.

## Company search and overviews

Under **Company or ticker not listed?**, **Find companies** searches Yahoo Finance only when clicked, returning up to eight equity listings with exchange labels. News and recommendations are disabled. **Open selected company** validates daily history before saving the company name. A known ticker can be entered directly; symbols are normalized and format-checked before provider use.

**Load company overview** is optional and button-driven. A complete saved database profile is reused for 30 days. After that, the button attempts a provider refresh. Failed or incomplete refreshes preserve the previous overview, which is marked older when returned as fallback. Successful profiles are saved within the company cap and shared through a bounded one-day memory cache. Browsing does not bulk-download missing overviews.

The starter JSON contains 20 companies. To refresh its profiles offline:

```bash
python scripts/refresh_companies.py --symbols AAPL MSFT
```

Review and commit successful JSON updates. Failed API refreshes preserve existing saved profiles. Runtime database updates do not modify repository files.

## Analysis and prediction

The dashboard shows period price return, standard deviation of daily returns, maximum drawdown, and summaries computed directly from prices. Comparisons align shared dates and start both series at 0% on their first shared date. Separate views provide line/candlestick charts, optional moving averages, volume, RSI, and MACD. Only the selected view runs; comparison requests require the **Compare stocks** button.

Forecasting predicts an endpoint return over 1–30 observed trading-session bars using past returns, moving-average distance, volatility, and relative volume. Ridge regression with training-fold standardization, an 80-tree regularized Random Forest, and 60 shallow gradient-boosted trees compete against an unchanged-price baseline in three expanding chronological development folds. Fixed hyperparameters limit computation and overfitting. The baseline wins exact ties.

All candidates use the same folds and mean absolute return error. Horizon-sized purge gaps prevent training labels from reaching validation or test origins. The best development method is tested on a separate latest holdout; test error is reported in percentage points. It is then refit using known historical labels to estimate the endpoint from the latest unlabelled row. At least 250 usable labelled rows are required. Only the selected method is refit, and the baseline requires no learned-model fit.

When persistence is available, a forecast is recorded once per `(symbol, as_of, horizon, model_version)`. Later normal price refreshes evaluate pending forecasts once enough future bars exist. Both observed-return endpoints use the same current adjusted-price basis. **View past estimates** shows up to 30 recent predictions, observed returns, and pending/evaluated status. It does not download extra market data. Missing provider bars can affect the mapping from bar count to actual exchange sessions; forecasts use the conservative completed-bar rule below.

Historical validation and later observations help assess the method; neither guarantees improved future accuracy. Overlapping multi-session targets are correlated. No confidence probability, synthetic daily price path, trading profit, or investment recommendation is claimed. Currency comes from the optional profile; otherwise values are labelled quote units.

## Resource controls and hosting

- History: four-hour memory cache, 48 entries; two years by default, five years only when selected.
- Profiles and company searches: one-day memory caches, 48 entries each. Saved dropdown catalog: one-hour cache, cleared when a company profile is explicitly remembered.
- Forecasts: one-day memory cache, 24 entries; button-driven, single CPU worker, one model computation at a time per process.
- Provider calls: one nonblocking network slot per process, 12-second timeout. Competing cold requests receive a retry message or saved-price fallback.
- Session cooldowns: 20 seconds for search, ticker lookup, comparisons, price retries, and forecasts; 60 seconds for overview lookup. These are basic resource controls, not complete abuse prevention.
- Database transactions: five-second connection timeout, three-second lock timeout, twelve-second statement timeout; manual cleanup allows fifteen seconds for statements.

These bounds reduce repeated work for visitors sharing tickers. They do not establish capacity for 100 simultaneous users or guarantee free-tier limits. Many different cold tickers can still hit provider rate limits. No paid service or new package is introduced.

Streamlit Community Cloud can hibernate inactive apps. A stopped app cannot wake itself. The platform's visible **Yes, get this app back up!** button can restart it. An already configured external browser visit provides best-effort waking; normal startup may refresh the selected stock under the rules above. It does not guarantee permanent uptime or bypass hosting policy.

## Validation

```bash
python -m pip install pytest
python -m pytest -q
```

Tests require neither production credentials nor live provider downloads. SQLite integration tests cover storage transactions, unique-row updates, refresh leases and token fencing, capacity reservations, profile preservation, forecast deduplication and evaluation, and weekly retention with rollback. Mocked market tests cover fresh database reuse, stale fallback, write failures, and five-year memory-only downloads. Streamlit tests cover company URL restoration, button-driven search/comparison/forecasting, and protected manual cleanup. Forecast tests check chronological purge boundaries, latest-row inference, and baseline fallback.

SQLite does not prove PostgreSQL row-lock behavior under real concurrent connections; the production SQL uses PostgreSQL row/advisory locks and conflict-aware inserts. A production load test and provider availability remain separate concerns.

## Efficient storage and forecast reuse

Price refreshes still download the full two-year window so historical corporate-action revisions are detected. PostgreSQL inserts missing rows and updates existing OHLCV rows only when a value differs. Unchanged price rows are left untouched; refresh timestamps still advance. Storage remains limited to 50 companies, 600 price rows per company and 5,000 forecast records. No background downloads run while Streamlit sleeps.

Forecast input and evaluation use daily bars at least **36 hours after their session-date midnight in UTC**. The app does not yet store exchange calendars or closing times, so this conservative buffer can exclude a completed recent bar and lag the chart. For example, a Friday-dated bar becomes eligible Saturday at 12:00 UTC. The completion filter is evaluated outside the memory cache, allowing eligibility to change without a new price download. This is a safety buffer, not a provider guarantee that bars cannot be revised.

Before training, the app looks for a saved forecast matching the company, eligible final date, horizon, model version, completion policy and fingerprint of all model-input dates, closes and volumes. A matching forecast is reused even after the app restarts. Revised input or a changed version creates a separate record within the existing forecast limit. The UI shows the forecast data date and whether the result was calculated or reused. Existing earlier forecasts remain readable. No schema migration or new package is required.

After unlocking the separate admin page, click **Refresh storage overview** to see saved company, price and forecast counts, limits, the last automatic cleanup and last price refresh. PostgreSQL also reports the whole database's size, including unrelated tables and indexes; this is not the Neon billing or compute quota. The overview is queried only on that button, requests no market data and starts no cleanup. Locking the page or deleting rows clears the overview snapshot. Deletion does not necessarily shrink physical files immediately; PostgreSQL reclaims old row versions through vacuuming.

## Plain-language price estimates

The **Price estimate** view explains the forecast in everyday language. **How many market trading days ahead?** counts trading days from the starting price date, excluding weekends and exchange holidays. **Calculate price estimate** runs the existing prediction methods; it adds no provider requests or new models.

The result shows **Estimated price after N trading days**, the starting price and its date, and the estimated percentage change. That percentage is a price change, not an accuracy or confidence score. A zero-change result explains when historical tests favored keeping the starting price; a rounded 0.00% can also represent a tiny nonzero prediction. Neither implies that the actual price will stay unchanged. Model comparisons and error definitions are inside **How did we check this estimate?**. **View past estimates** uses readable labels for waiting and completed comparisons. Forecast calculation, storage, validation and retention rules are unchanged.
