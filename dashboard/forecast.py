"""Small CPU forecast with purged chronological validation and untouched holdout."""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit


def prepare_features(df):
    if not {'Date', 'Close', 'Volume'}.issubset(df.columns):
        raise ValueError('Date, Close and Volume are required.')
    frame = df.copy()
    frame['Date'] = pd.to_datetime(frame['Date'], errors='raise')
    if frame.Date.isna().any():
        raise ValueError('Price dates contain missing values.')
    frame = frame.sort_values('Date').drop_duplicates('Date').reset_index(drop=True)
    if frame[['Close', 'Volume']].isna().any().any() or (frame.Close <= 0).any() or (frame.Volume < 0).any():
        raise ValueError('Prices and volumes contain invalid values.')
    returns = frame.Close.pct_change(fill_method=None)
    features = pd.DataFrame(index=frame.index)
    for lag in (1, 2, 5, 10, 20):
        features[f'return_{lag}'] = frame.Close.pct_change(lag, fill_method=None)
    for window in (5, 10, 20):
        features[f'volatility_{window}'] = returns.rolling(window).std()
        features[f'ma_distance_{window}'] = frame.Close / frame.Close.rolling(window).mean() - 1
    # Relative volume avoids raw price/volume scale dominating across time.
    features['relative_volume'] = frame.Volume / frame.Volume.rolling(20).mean().replace(0, np.nan) - 1
    return frame, features.replace([np.inf, -np.inf], np.nan)


def new_model():
    return RandomForestRegressor(n_estimators=80, max_depth=6, min_samples_leaf=10,
                                 max_features=0.8, random_state=42, n_jobs=1)


def forecast(df, horizon=7):
    if not isinstance(horizon, int) or not 1 <= horizon <= 30:
        raise ValueError('Horizon must be 1–30 trading sessions.')
    frame, features = prepare_features(df)
    target = frame.Close.shift(-horizon) / frame.Close - 1
    mask = features.notna().all(axis=1) & target.notna()
    X, y = features.loc[mask], target.loc[mask]
    if len(X) < 250 or features.iloc[-1].isna().any():
        return {'available': False, 'reason': 'At least 250 usable history rows and valid latest features are needed.'}
    holdout_size = max(40, len(X) // 5)
    split = len(X) - holdout_size
    dev_X, dev_y = X.iloc[:split-horizon], y.iloc[:split-horizon]
    test_X, test_y = X.iloc[split:], y.iloc[split:]
    # Select on development folds only. Purge labels spanning the next test origin.
    model_errors, baseline_errors = [], []
    fold_ranges = []
    for train, valid in TimeSeriesSplit(n_splits=3, gap=horizon).split(dev_X):
        model = new_model().fit(dev_X.iloc[train], dev_y.iloc[train])
        model_errors.extend(np.abs(model.predict(dev_X.iloc[valid]) - dev_y.iloc[valid]))
        baseline_errors.extend(np.abs(dev_y.iloc[valid]))
        fold_ranges.append({'train_last': int(dev_X.index[train[-1]]), 'valid_first': int(dev_X.index[valid[0]])})
    use_model = np.mean(model_errors) < np.mean(baseline_errors)
    model = new_model().fit(dev_X, dev_y)
    test_prediction = model.predict(test_X) if use_model else np.zeros(len(test_X))
    # Report honest out-of-sample errors even when the selected model loses here.
    error = np.asarray(test_y) - test_prediction
    mae = float(np.mean(np.abs(error)))
    baseline_mae = float(np.mean(np.abs(test_y)))
    # Refit with all now-known labels; inference uses the latest UNLABELLED row.
    latest_return = float(new_model().fit(X, y).predict(features.iloc[[-1]])[0]) if use_model else 0.0
    last_price = float(frame.Close.iloc[-1])
    return {
        'available': True, 'model': 'Random Forest' if use_model else 'Unchanged-price baseline',
        'predicted_price': last_price * (1 + latest_return), 'predicted_return': latest_return,
        'mae_pct': 100 * mae, 'baseline_mae_pct': 100 * baseline_mae,
        'beats_baseline_on_holdout': mae < baseline_mae,
        'direction_accuracy': float(np.mean(np.sign(test_prediction) == np.sign(test_y))) if use_model else None,
        'as_of': str(frame.Date.iloc[-1]), 'training_rows': len(X), 'test_rows': len(test_X),
        'test_start': str(frame.loc[test_X.index[0], 'Date']), 'test_end': str(frame.loc[test_X.index[-1], 'Date']),
        'train_last_origin': int(dev_X.index[-1]), 'test_first_origin': int(test_X.index[0]),
        'latest_feature_origin': int(features.index[-1]), 'fold_ranges': fold_ranges,
    }
