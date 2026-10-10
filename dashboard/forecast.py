"""Small CPU forecast with purged chronological validation and untouched holdout."""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
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


def model_factories():
    # Fit preprocessing inside each training fold; never scale using future rows.
    return {'Ridge regression': lambda: make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
            'Random Forest': new_model,
            'Gradient boosting': lambda: GradientBoostingRegressor(
                n_estimators=60, max_depth=2, min_samples_leaf=15,
                learning_rate=0.03, loss='huber', random_state=42)}


def forecast(df, horizon=7):
    if not isinstance(horizon, int) or not 1 <= horizon <= 504:
        raise ValueError('Choose between 1 and 504 trading days.')
    frame, features = prepare_features(df)
    target = frame.Close.shift(-horizon) / frame.Close - 1
    mask = features.notna().all(axis=1) & target.notna()
    X, y = features.loc[mask], target.loc[mask]
    if len(X) < 250 or features.iloc[-1].isna().any():
        return {'available': False, 'reason': 'There is not enough historical data for this time period. We need at least 250 examples with known later prices. Choose a shorter period; no extra history is downloaded automatically.'}
    holdout_size = max(40, len(X) // 5)
    split = len(X) - holdout_size
    dev_X, dev_y = X.iloc[:split-horizon], y.iloc[:split-horizon]
    test_X, test_y = X.iloc[split:], y.iloc[split:]
    # Long horizons need wider initial training windows while preserving three purged folds.
    splitter = TimeSeriesSplit(n_splits=3, gap=horizon)
    initial_train = len(dev_X) - 3 * (len(dev_X)//4) - horizon
    if initial_train < 50:
        test_size = max(20, len(dev_X)//6)
        if len(dev_X) - 3*test_size - horizon < 50:
            return {'available': False, 'reason': 'There is not enough historical data to safely test this longer estimate. Choose a shorter period. The app keeps two years of forecast history and does not automatically download more.'}
        splitter = TimeSeriesSplit(n_splits=3, gap=horizon, test_size=test_size)
    # Select on development folds only. Purge labels spanning the next test origin.
    baseline = 'Unchanged-price baseline'
    factories = model_factories()
    errors = {name: [] for name in [baseline, *factories]}
    fold_ranges = []
    for train, valid in splitter.split(dev_X):
        errors[baseline].extend(np.abs(dev_y.iloc[valid]))
        for name, factory in factories.items():
            model = factory().fit(dev_X.iloc[train], dev_y.iloc[train])
            errors[name].extend(np.abs(model.predict(dev_X.iloc[valid]) - dev_y.iloc[valid]))
        fold_ranges.append({'train_last': int(dev_X.index[train[-1]]), 'valid_first': int(dev_X.index[valid[0]])})
    validation_mae = {name: float(np.mean(values)) for name, values in errors.items()}
    # Baseline wins exact ties. The holdout never selects a method or its settings.
    selected = min(validation_mae, key=validation_mae.get)
    use_model = selected != baseline
    test_prediction = factories[selected]().fit(dev_X, dev_y).predict(test_X) if use_model else np.zeros(len(test_X))
    # Report honest out-of-sample errors even when the selected model loses here.
    error = np.asarray(test_y) - test_prediction
    mae = float(np.mean(np.abs(error)))
    baseline_mae = float(np.mean(np.abs(test_y)))
    # Refit with all now-known labels; inference uses the latest UNLABELLED row.
    latest_return = float(factories[selected]().fit(X, y).predict(features.iloc[[-1]])[0]) if use_model else 0.0
    last_price = float(frame.Close.iloc[-1])
    if not np.isfinite(latest_return) or latest_return <= -1:
        return {'available': False, 'reason': 'The selected method produced an invalid endpoint. No estimate is shown.'}
    return {
        'available': True, 'model': selected,
        'validation_scores': [{'method': name, 'mae_pct': 100 * score, 'selected': name == selected}
                              for name, score in validation_mae.items()],
        'validation_rows': len(errors[baseline]), 'input_rows': len(frame),
        'feature_rows': int(features.notna().all(axis=1).sum()),
        'history_start': str(frame.Date.iloc[0]), 'horizon': horizon,
        'predicted_price': last_price * (1 + latest_return), 'predicted_return': latest_return,
        'mae_pct': 100 * mae, 'baseline_mae_pct': 100 * baseline_mae,
        'beats_baseline_on_holdout': mae < baseline_mae,
        'direction_accuracy': float(np.mean(np.sign(test_prediction) == np.sign(test_y))) if use_model else None,
        'as_of': str(frame.Date.iloc[-1]), 'training_rows': len(X), 'test_rows': len(test_X),
        'test_start': str(frame.loc[test_X.index[0], 'Date']), 'test_end': str(frame.loc[test_X.index[-1], 'Date']),
        'train_last_origin': int(dev_X.index[-1]), 'test_first_origin': int(test_X.index[0]),
        'latest_feature_origin': int(features.index[-1]), 'fold_ranges': fold_ranges,
    }
