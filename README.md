# Stock Explorer

A lightweight Streamlit dashboard for understanding historical stock performance and price risk. Its main views show price changes, price swings, drops from earlier peaks, and company comparisons. Prediction is a secondary experiment, not the main product promise. Optional Neon PostgreSQL storage shares data across visitors and survives app restarts. The app uses one CPU process, no LLM calls, and no separate model server.

## Project structure

| Path | Purpose |
| --- | --- |
| `dashboard/app.py` | Streamlit entry point; registers the dashboard and separate admin page. |
| `dashboard/home.py` | Company search, performance and risk views, comparisons, charts and prediction controls. |
| `dashboard/analysis.py` | Historical performance, price variation and peak-drop calculations. |
| `dashboard/forecast.py` | Prediction features, models, chronological testing and acceptance checks. |
| `dashboard/market.py` | Provider requests, price and profile caches, saved-price reuse and forecast reuse. |
| `dashboard/catalog.py` | Reads the starter company names and profiles from JSON. |
| `dashboard/storage.py` | Optional database connection and shared-storage adapters. |
| `dashboard/runtime.py` | Applies adapter versions and clears older caches once after an update. |
| `dashboard/pages/admin.py` | Separate database administration page. |
| `dashboard/database_admin.py` | Administrator authentication, storage overview and manual price cleanup. |
| `etl/shared_store.py` | Managed database tables, price upserts, refresh coordination, forecasts and retention. |
| `etl/cleanup.py` | Validates and deletes selected saved price rows for the admin controls. |
| `etl/extract.py`, `etl/transform.py`, `etl/load.py` | Earlier ETL utilities retained for compatibility; the current dashboard uses the shared store instead of replace-table exports. |
| `data/companies.json` | Starter company names and optional saved overview fields. |
| `scripts/refresh_companies.py` | Explicit offline refresh of starter company profiles. |
| `scripts/evaluate_models.py` | Bounded offline prediction study using exported price CSVs. |
| `analysis/` | Dated model-study report and JSON results. |
| `tests/` | Dashboard, market, forecast, storage, cleanup, runtime and study checks. |
| `requirements.txt` | Pinned Python dependencies. |
| `Dockerfile`, `docker-compose.yml` | Container setup and an optional local PostgreSQL service. |

Start with `dashboard/app.py` when running the app. Follow `dashboard/home.py` for UI behavior and `etl/shared_store.py` for how saved data is managed.

## Installation and local setup

### Requirements

Use Python **3.11 or 3.12**, Git, and an internet connection for market-data downloads. Python 3.12 was used for the project test run; the existing Docker image uses Python 3.11. A database is optional: you can explore stocks without Neon, but data in memory does not survive app restarts. No LLM API key is needed. Docker is only required for the container option below.

### 1. Get the project

```bash
git clone https://github.com/bhuwanbkt/stock-analysis-dashboard_cloud.git
cd stock-analysis-dashboard_cloud
```

If Git is unavailable, download the repository ZIP from GitHub, extract it and open a terminal inside the extracted project folder.

### 2. Create an environment and install packages

On **macOS or Linux**:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On **Windows PowerShell**, use Python 3.12 and the environment's Python directly; activation is not required:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Run the dashboard

Run from the **project root**, where `requirements.txt` is located.

On macOS or Linux, with the environment activated:

```bash
python -m streamlit run dashboard/app.py
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py
```

Open `http://localhost:8501` (or the local URL printed in the terminal). Select a company to view its history. Comparisons and predictions run only when their buttons are clicked. Stop the app with **Ctrl+C**. To start it again later, return to the same folder and run the same command; there is no need to reinstall packages each time.

### 4. Optional: enable Neon persistence and admin access

Copy the PostgreSQL connection string from your Neon project's connection details. Keep its SSL settings, such as `sslmode=require`. The app reads top-level Streamlit secrets first, then environment variables. These examples use environment variables so credentials do not need to be saved in a repository file.

On macOS or Linux, set these in the same terminal before starting Streamlit:

```bash
export DATABASE_URL='your Neon PostgreSQL connection URL'
export DATABASE_ADMIN_TOKEN='your private administrator password of at least 24 characters'
python -m streamlit run dashboard/app.py
```

On Windows PowerShell:

```powershell
$env:DATABASE_URL = 'your Neon PostgreSQL connection URL'
$env:DATABASE_ADMIN_TOKEN = 'your private administrator password of at least 24 characters'
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py
```

Replace the placeholder values before running. `DATABASE_ADMIN_TOKEN` is optional unless you want manual cleanup. Generate it once, save it privately, and reuse it; it is separate from the Neon password. For example, Python can generate a random 64-character token:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

On Windows, run that command with `.\.venv\Scripts\python.exe` instead of `python`. Terminal environment settings last for that terminal session; set them again in a new terminal. A `.env` file is **not automatically loaded** by this app. If you choose local Streamlit secrets instead, create `.streamlit/secrets.toml` in the project root and exclude it from Git before adding credentials. The committed `.gitignore` currently does not explicitly exclude that file. Do not commit credentials or include them in container images.

On a successful connection, the app creates its managed tables automatically. No separate migration command or daily download job is needed. Use **Open admin page** at the top of the sidebar for the storage overview and cleanup. See [Bounded shared storage](#bounded-shared-storage) and [Manual removal of old and new prices](#manual-removal-of-old-and-new-prices) for limits and deletion behavior.

### Alternative: Docker with local PostgreSQL

The repository includes a Dockerfile and Compose services for the app and PostgreSQL 15. The current app requires **`DATABASE_URL`**; the older `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` and `DB_PASSWORD` entries in Compose do not configure its shared store on their own.

For local development, create `docker-compose.override.yml` in the project root with:

```yaml
services:
  stock-dashboard:
    environment:
      DATABASE_URL: postgresql://postgres:password@postgres:5432/stocks
```

This matches the existing local database service's development credentials. The override filename is ignored by Git. For manual cleanup, also add a private `DATABASE_ADMIN_TOKEN` under that service's `environment`; keep it out of Git and any image build context. A secrets file, if present, takes precedence over these environment settings.

```bash
docker compose up --build -d
docker compose logs -f stock-dashboard
```

Open `http://localhost:8501`. Ctrl+C exits the log viewer while the containers keep running. To stop them:

```bash
docker compose down
```

The named `postgres_data` volume retains local records after a normal shutdown. The existing Compose setup exposes host ports 8501 and 5432, so those ports must be available. Its fixed database password is for local development; do not expose this setup publicly. Docker startup is documented from the existing configuration and has not been exercised in the hosted editing environment.

### Streamlit Community Cloud setup

1. Connect this GitHub repository and choose the `main` branch.
2. Set the main file path to **`dashboard/app.py`** and use Python 3.11 or 3.12.
3. Add optional top-level `DATABASE_URL` and `DATABASE_ADMIN_TOKEN` values under the app's **Settings → Secrets**, using the TOML examples below. Hosted secrets persist across sleep and restart.
4. Deploy the app. Dependencies are installed from the root `requirements.txt`; Docker Compose is not used by Community Cloud.

No database settings are needed for the memory-only dashboard. See [Resource controls and hosting](#resource-controls-and-hosting) for sleep behavior and resource limits.

### Common setup problems

| Problem | What to check |
| --- | --- |
| Package installation fails | Check the Python version, use a fresh virtual environment, upgrade pip and install from the pinned requirements. |
| `streamlit` or another module is missing | Run with the same environment's Python used to install the packages. |
| No prices appear | Check internet access and the provider warning; a rate limit or outage can prevent downloads. Try a known starter company. |
| Prices are shown but not saved | Check `DATABASE_URL`, database permissions and any database warning. API/memory fallback can still display prices. |
| Admin controls stay locked | Configure both database URL and an administrator token of at least 24 characters, then restart the local app. |
| Compose cannot bind a port | Stop the conflicting local service or change the host-side port mapping in a private override. |

For tests, see [Validation](#validation). For the offline prediction study, see [Small offline model study](#small-offline-model-study).

## What happens when someone opens the app

1. The dropdown combines the starter names in `data/companies.json`, saved database companies, and up to ten additional listings in the current session. Searching this dropdown makes no company-search API call.
2. The selected stock first uses the shared four-hour memory cache. On a cache miss, the app checks Postgres when configured.
3. Saved five-year prices downloaded less than 24 hours ago are reused without a provider download. Missing or older prices trigger a download for **that selected stock only**. There is no daily job downloading every saved company.
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
| `stock_daily_prices` | Adjusted daily OHLCV, unique `(symbol, Date)` | Rolling five calendar years; at most 1,500 rows per company |
| `stock_refresh_status` | Last download, lease token, retry state | Saved companies plus bounded transient failed lookups; expired transient rows removed on refresh claims |
| `stock_forecast_runs` | Forecast result and later observed return | 90 days; hard maximum 5,000 records |
| `stock_maintenance` | Capacity coordination, weekly cleanup and history-upgrade markers | Two coordination rows plus one marker per saved company (up to 50) |

Typical five-year equity history is around 1,260 daily rows per company, or around 63,000 price rows across 50 companies. The hard price cap is 75,000 rows. Exact storage bytes include profiles, forecasts, indexes, and PostgreSQL overhead; these are row bounds, not a promised database size or provider quota. Existing export tables count toward your Neon usage separately.

At the company limit, new stocks can still be viewed in memory but are not saved, and the UI explains this. The app does not automatically evict saved companies. Unknown tickers with failed history downloads do not become saved companies. Charts and forecasts share the same saved five-year history. Forecasts use at most the latest five years of eligible supplied prices. Newer listings may have less history.

A refresh downloads the complete five-year provider window, rather than only the latest day. This is a deliberate tradeoff: corporate actions can revise previously adjusted prices, so successful refreshes replace values for matching dates and remove dates absent from the current snapshot. Invalid or incomplete responses are not persisted. CSV download is available for the selected chart period.

Connections use `NullPool`, closing client connections after each transaction instead of holding an idle connection open. Database errors fall back to API/memory when possible; fallback data is explicitly labelled and is not guaranteed to survive a restart. A database outage can increase provider calls after cache expiration. Refresh leases coordinate only when shared storage is available; the network and model semaphores apply per app process.

## Cleanup and sleeping apps

Automatic cleanup checks a **database-persisted timestamp**. When seven days have elapsed since the last successful cleanup, an active visit removes prices outside the five-year window and forecast records older than 90 days. Deletes and the timestamp update commit together; a failed cleanup rolls back and does not advance the timestamp. An hourly memory gate avoids checking maintenance on every rerun; a restarted process checks again. A successful price refresh also prunes that ticker immediately.

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

Forecasting can predict an endpoint return over 1–63 observed trading-session bars (up to about three months) using past returns, moving-average distance, volatility, and relative volume. Ridge regression with training-fold standardization, an 80-tree regularized Random Forest, and 60 shallow gradient-boosted trees compete against an unchanged-price baseline in three expanding chronological development folds. Fixed hyperparameters limit computation and overfitting. The baseline wins exact ties; it is a testing benchmark and is never displayed as a new prediction.

All candidates use the same folds and mean absolute return error. Horizon-sized purge gaps prevent training labels from reaching validation or test origins. The best development method is tested on a separate latest holdout with at least as many starting dates as the forecast horizon; test error is reported in percentage points. A learned model must beat the no-change benchmark in both development and the recent holdout. Otherwise the UI says **No model passed our prediction check**, shows testing details on request, and provides no endpoint price or 0% placeholder. The holdout does not choose another model or tune its settings. Only a passing model is refit using known historical labels to estimate the endpoint from the latest unlabelled row. At least 250 usable labelled rows and 50 initial-fold training examples are required. Passing these checks is not proof of statistical significance or future accuracy; overlapping targets are correlated.

Only accepted predictions are persisted. Failed checks remain in the bounded one-day memory cache, avoiding repeated training in the same running process. When persistence is available, a forecast is recorded once per `(symbol, as_of, horizon, model_version)`. Later normal price refreshes evaluate pending forecasts once enough future bars exist. Both observed-return endpoints use the same current adjusted-price basis. **View past estimates** shows up to 30 recent predictions, observed returns, and pending/evaluated status. It does not download extra market data. Missing provider bars can affect the mapping from bar count to actual exchange sessions; forecasts use the conservative completed-bar rule below.

Historical validation and later observations help assess the method; neither guarantees improved future accuracy. Overlapping multi-session targets are correlated. No confidence probability, synthetic daily price path, trading profit, or investment recommendation is claimed. Currency comes from the optional profile; otherwise values are labelled quote units.

## Resource controls and hosting

- History: four-hour memory cache, 48 entries; five years shared by every chart period.
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

Tests require neither production credentials nor live provider downloads. SQLite integration tests cover storage transactions, unique-row updates, refresh leases and token fencing, capacity reservations, profile preservation, forecast deduplication and evaluation, and weekly retention with rollback. Mocked market tests cover fresh database reuse, stale fallback, write failures, and five-year shared downloads and upgrades from older saved snapshots. Streamlit tests cover company URL restoration, button-driven search/comparison/forecasting, and protected manual cleanup. Forecast tests check chronological purge boundaries, latest-row inference, and rejection when a model fails either benchmark check.

SQLite does not prove PostgreSQL row-lock behavior under real concurrent connections; the production SQL uses PostgreSQL row/advisory locks and conflict-aware inserts. A production load test and provider availability remain separate concerns.

## Efficient storage and forecast reuse

Price refreshes still download the full five-year window so historical corporate-action revisions are detected. PostgreSQL inserts missing rows and updates existing OHLCV rows only when a value differs. Unchanged price rows are left untouched; refresh timestamps still advance. Storage remains limited to 50 companies, 1,500 price rows per company and 5,000 forecast records. No background downloads run while Streamlit sleeps.

Forecast input and evaluation use daily bars at least **36 hours after their session-date midnight in UTC**. The app does not yet store exchange calendars or closing times, so this conservative buffer can exclude a completed recent bar and lag the chart. For example, a Friday-dated bar becomes eligible Saturday at 12:00 UTC. The completion filter is evaluated outside the memory cache, allowing eligibility to change without a new price download. This is a safety buffer, not a provider guarantee that bars cannot be revised.

Before training, the app looks for a saved forecast matching the company, eligible final date, horizon, model version, completion policy and fingerprint of all model-input dates, closes and volumes. A matching forecast is reused even after the app restarts. Revised input or a changed version creates a separate record within the existing forecast limit. The UI shows the forecast data date and whether the result was calculated or reused. Existing earlier forecasts remain readable. No schema migration or new package is required.

After unlocking the separate admin page, click **Refresh storage overview** to see saved company, price and forecast counts, limits, the last automatic cleanup and last price refresh. PostgreSQL also reports the whole database's size, including unrelated tables and indexes; this is not the Neon billing or compute quota. The overview is queried only on that button, requests no market data and starts no cleanup. Locking the page or deleting rows clears the overview snapshot. Deletion does not necessarily shrink physical files immediately; PostgreSQL reclaims old row versions through vacuuming.

## Plain-language price estimates

The **Prediction experiment** view explains model testing in everyday language. A failed check is an experiment result, while Overview and Compare remain useful for historical analysis. **How far ahead would you like to estimate?** counts trading days from the starting price date, excluding weekends and exchange holidays. **Calculate price estimate** runs the existing prediction methods; it adds no provider requests or new models.

The result shows **Estimated price after N trading days**, the starting price and its date, and the estimated percentage change. That percentage is a price change, not an accuracy or confidence score. If no model passes both benchmark checks, no predicted-price card or 0% placeholder is shown. An accepted model may still have a very small return that rounds to 0.00%; this does not imply the actual price will stay unchanged. Accepted results show the recent average testing error beside the estimate. Model comparisons and error definitions are inside **How did we check this estimate?**. **View past estimates** uses readable labels for waiting and completed comparisons. Older saved results remain readable and are marked as predating the current check. New failed checks are not saved as predictions.


Estimate periods include days, weeks and 1/2/3 months. Month choices use about 21 trading days per month; these are not exact calendar dates. Six-month and year options have been removed from this resource-limited model. Three chronological folds retain horizon-sized gaps, and smaller validation windows are used if needed to preserve at least 50 initial-fold training examples. An insufficient-history message appears when safe testing is impossible.

## Five-year history upgrade

The next active request for each existing saved stock treats its earlier two-year snapshot as stale and requests a five-year snapshot, even if its last download was recent. No all-company backfill runs. A small marker in the existing `stock_maintenance` table records each successful five-year refresh; no schema migration is needed. For newer listings, a successful shorter available history also receives the marker, preventing continuous backfill requests. Failed refreshes keep the old saved prices visible, with a stale-data notice and the existing retry backoff. A later visit can retry.

After that upgrade, the same 24-hour shared freshness rule applies. Chart-period changes use the same history and do not cause separate two-year/five-year downloads. A refresh still downloads the full five-year daily window to catch adjusted-price revisions, but existing database rows update only if values changed. Prices are unique by company and date; the saved window rolls rather than growing forever. Cleanup remains due every seven days and runs on an active visit; a sleeping app performs no downloads or cleanup. The five-year cutoff and 1,500-row per-company cap are applied on each successful refresh. Profiles, the 50-company limit, and 90-day/5,000-row forecast retention are unchanged. The separate admin page still supports manual deletion.

Forecast reuse has a new model-version identity, so older unchanged-price results cannot become new accepted predictions. The saved-store resource version also changes. At the first page startup for a runtime generation, a version check reloads older imported data adapters and the forecast module in dependency order if needed, then clears memory caches once (even when imports already match), so a multipage deployment can apply the new rules without relying on a process restart. Normal reruns and cold starts do not reload current adapters; admin startup performs no database or provider requests. Future changes to these adapter contracts should bump the matching `RUNTIME_VERSION` in `dashboard/runtime.py`, `dashboard/forecast.py`, `dashboard/market.py`, `dashboard/storage.py` and `etl/shared_store.py`. More historical data increases download, memory and database use, but does not guarantee smaller errors or a prediction for every company.

## Performance and risk first

Overview shows **Price change**, **Daily price variation** (standard deviation of daily percentage changes), and **Largest drop from a peak**. Plain-language help explains each number and its limits. The latest close's distance below the highest close in the selected period distinguishes the current position from the largest historical drop. These use provider-adjusted closing prices and do not calculate an investor's actual profit after cash payments, fees and taxes.

Compare adds a side-by-side price-change, price-variation and peak-drop table calculated on exactly the shared dates used by its chart. Its variation statistic uses changes between consecutive shared dates, which can span more than one trading day when holidays or missing bars differ. Chart controls, saved prices, cleanup and provider request limits remain unchanged. Prediction has moved to **Prediction experiment** and does not run until its button is clicked.

## Small offline model study

The saved [study report](analysis/model-study-2026-10-10.md) and [machine-readable results](analysis/model-study-2026-10-10.json) evaluate AAPL, MSFT and JPM at three historical cutoffs, for 5-, 21- and 42-trading-day horizons: 27 checks. **None passed both benchmark checks** in this sample. This supports keeping prediction experimental; it does not prove that all stock forecasting methods fail. No model settings or acceptance rules were changed after seeing the results. The Prediction experiment view includes a clearly dated summary of this fixed study.

Run the same bounded study using exported five-year daily CSVs:

```bash
python scripts/evaluate_models.py \
  --csv AAPL=/path/to/AAPL_daily_prices.csv \
  --csv MSFT=/path/to/MSFT_daily_prices.csv \
  --csv JPM=/path/to/JPM_daily_prices.csv \
  --as-of 2026-10-10T05:45:00Z \
  --output analysis/model-study.json
```

The script uses no API calls or database writes. It allows up to three stocks, three horizons and three historical snapshots; default snapshots remove 504, 252 and zero latest eligible rows. Models use the existing fixed settings, chronological purge gaps, separate recent holdout and completion buffer. JSON includes input fingerprints and testing dates; Markdown contains a readable result table. Forecasts for the current latest row are not recorded in Neon.

The exports are currently adjusted historical prices, not archived point-in-time vintages. Snapshot histories have different lengths, some holdout periods overlap, and multi-day targets overlap within tests. The three stocks were deliberately chosen rather than sampled randomly. Pass counts are not accuracy percentages, independent trials, significance tests or proof of trading profit. Raw price CSVs remain local inputs and are not committed. Running this study again is a deliberate offline action, not a visitor-triggered job.
