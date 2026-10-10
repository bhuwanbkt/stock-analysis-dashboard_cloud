# Small historical model study

Data cutoff: 2026-10-10T05:45:00+00:00. Source: Daily CSV exports from Stock Explorer / Yahoo Finance via yfinance.

0 of 27 stock/period/horizon checks passed both benchmark checks.

This count is an acceptance result, not prediction accuracy.

| Stock | History ending | Trading days ahead | Best learned method in earlier tests | Model error (pp) | No-change error (pp) | Passed both checks? |
| --- | --- | ---: | --- | ---: | ---: | --- |
| AAPL | 2024-10-03 | 5 | Ridge regression | 3.07 | 2.86 | No |
| AAPL | 2024-10-03 | 21 | Gradient boosting | 7.16 | 6.23 | No |
| AAPL | 2024-10-03 | 42 | Gradient boosting | 10.50 | 9.13 | No |
| AAPL | 2025-10-07 | 5 | Ridge regression | 2.81 | 2.72 | No |
| AAPL | 2025-10-07 | 21 | Ridge regression | 6.02 | 5.62 | No |
| AAPL | 2025-10-07 | 42 | Ridge regression | 9.48 | 8.89 | No |
| AAPL | 2026-10-08 | 5 | Ridge regression | 2.96 | 2.94 | No |
| AAPL | 2026-10-08 | 21 | Ridge regression | 5.92 | 5.82 | No |
| AAPL | 2026-10-08 | 42 | Ridge regression | 8.89 | 8.31 | No |
| MSFT | 2024-10-03 | 5 | Gradient boosting | 3.16 | 2.90 | No |
| MSFT | 2024-10-03 | 21 | Random Forest | 7.40 | 6.22 | No |
| MSFT | 2024-10-03 | 42 | Ridge regression | 12.30 | 8.74 | No |
| MSFT | 2025-10-07 | 5 | Gradient boosting | 2.78 | 2.64 | No |
| MSFT | 2025-10-07 | 21 | Random Forest | 6.04 | 5.36 | No |
| MSFT | 2025-10-07 | 42 | Ridge regression | 10.88 | 7.77 | No |
| MSFT | 2026-10-08 | 5 | Gradient boosting | 2.70 | 2.49 | No |
| MSFT | 2026-10-08 | 21 | Ridge regression | 6.33 | 5.41 | No |
| MSFT | 2026-10-08 | 42 | Ridge regression | 10.10 | 8.25 | No |
| JPM | 2024-10-03 | 5 | Gradient boosting | 2.86 | 2.54 | No |
| JPM | 2024-10-03 | 21 | Gradient boosting | 7.86 | 5.75 | No |
| JPM | 2024-10-03 | 42 | Gradient boosting | 12.08 | 8.03 | No |
| JPM | 2025-10-07 | 5 | Gradient boosting | 3.01 | 2.51 | No |
| JPM | 2025-10-07 | 21 | Gradient boosting | 7.21 | 5.75 | No |
| JPM | 2025-10-07 | 42 | Gradient boosting | 10.76 | 7.80 | No |
| JPM | 2026-10-08 | 5 | Gradient boosting | 2.79 | 2.47 | No |
| JPM | 2026-10-08 | 21 | Gradient boosting | 6.38 | 5.58 | No |
| JPM | 2026-10-08 | 42 | Gradient boosting | 10.22 | 8.43 | No |

The table compares errors in earlier development tests. Errors measure percentage points of future price change; smaller is better. JSON includes every candidate score and the separate recent test results.

Models are chosen on earlier tests. The recent holdout only accepts or rejects that choice; it does not choose a replacement model.

Limitations:
- Only three deliberately chosen US stocks; not representative of all markets.
- Historical snapshots use currently adjusted prices, not archived point-in-time provider vintages.
- Test targets and some snapshot windows overlap; counts are not independent trials.
- Passing an error comparison does not establish statistical significance or future trading profit.
- No hyperparameters or acceptance thresholds were changed after seeing these results.
