import json
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch
from dashboard.forecast import forecast, prepare_features
from dashboard.catalog import load_catalog, search_catalog
from scripts.refresh_companies import refresh


def history(n=510):
    rng = np.random.default_rng(42)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n)))
    return pd.DataFrame({'Date': pd.bdate_range('2023-01-01', periods=n), 'Close': close,
                         'Volume': rng.integers(100000, 200000, n)})


@pytest.mark.parametrize('horizon', [1, 7, 30, 42, 63])
@pytest.mark.parametrize('rows', [510, 1260])
def test_forecast_no_label_leakage_and_latest_inference(horizon, rows):
    data = history(rows)
    result = forecast(data, horizon)
    assert result['train_last_origin'] + horizon < result['test_first_origin']
    for fold in result['fold_ranges']:
        assert fold['train_last'] + horizon < fold['valid_first']
    assert result['latest_feature_origin'] == len(data) - 1
    assert result['as_of'] == str(data.Date.iloc[-1])
    assert result['test_rows'] >= horizon
    if result['available']:
        assert result['model'] != 'Unchanged-price baseline'
        assert result['beats_baseline_on_holdout']
        assert np.isfinite(result['predicted_price']) and result['predicted_price'] > 0
    else:
        assert 'predicted_price' not in result and 'predicted_return' not in result
        assert result['status'] == 'rejected'
    assert result['mae_pct'] >= 0


def test_features_do_not_depend_on_future_prices():
    data = history()
    _, before = prepare_features(data)
    data.loc[400:, 'Close'] *= 2
    _, after = prepare_features(data)
    pd.testing.assert_frame_equal(before.iloc[:400], after.iloc[:400])


def test_short_history_and_invalid_input():
    assert not forecast(history(100))['available']
    with pytest.raises(ValueError):
        forecast(history(), 0)
    data = history()
    data.loc[10, 'Close'] = 0
    with pytest.raises(ValueError):
        forecast(data)


def test_catalog_search_and_refresh_failure_preserve_profile(tmp_path):
    path = tmp_path / 'companies.json'
    row = {'symbol': 'AAPL', 'name': 'Apple Inc.', 'overview': 'Saved profile', 'updated_at': 'old'}
    path.write_text(json.dumps({'companies': [row]}))
    catalog = load_catalog(path)
    assert search_catalog(catalog, ' apple ') == ['AAPL']
    assert search_catalog(catalog, 'aapl') == ['AAPL']
    assert search_catalog(catalog, 'no match') == []
    assert refresh(path, fetch=lambda symbol: {}) == ['AAPL']
    assert load_catalog(path)['AAPL'] == row
    assert refresh(path, fetch=lambda symbol: {'longName': 'Apple Inc.', 'longBusinessSummary': 'API overview', 'sector': 'Technology'}) == []
    saved = load_catalog(path)['AAPL']
    assert saved['overview'] == 'API overview'
    assert saved['updated_at'] != 'old'
    assert saved['source'] == 'Yahoo Finance via yfinance'


def test_constant_prices_select_unchanged_baseline():
    data = history()
    data['Close'] = 100.0
    result = forecast(data)
    assert result['model'] == 'Unchanged-price baseline'
    assert not result['available']
    assert 'predicted_price' not in result
    assert 'No model passed' in result['reason']
    assert result['mae_pct'] == 0.0
    assert result['direction_accuracy'] is None


def test_holdout_does_not_choose_the_method():
    data = history()
    data['Close'] = 100.0
    data.loc[430:, 'Close'] = 100 * np.exp(np.arange(80) * .004)

    class Constant:
        def __init__(self, value): self.value = value
        def fit(self, X, y): return self
        def predict(self, X): return np.full(len(X), self.value)

    with patch('dashboard.forecast.model_factories', return_value={
        'Ridge regression': lambda: Constant(.02),
        'Random Forest': lambda: Constant(.03),
        'Gradient boosting': lambda: Constant(.04)}):
        result = forecast(data, 7)
    assert result['model'] == 'Unchanged-price baseline'
    assert not result['available'] and 'predicted_price' not in result
    assert next(row for row in result['validation_scores'] if row['selected'])['mae_pct'] == 0
    target = data.Close.shift(-7) / data.Close - 1
    test_targets = target.loc[result['test_first_origin']:].dropna()
    # A candidate would have won on this later window, but it cannot alter selection.
    assert np.mean(np.abs(test_targets - .02)) < np.mean(np.abs(test_targets))


def test_all_candidates_share_folds_and_only_winner_gets_refit():
    data = history()
    data['Close'] = 100 * np.exp(np.arange(len(data)) * .001)
    fits = {name: [] for name in ['Ridge regression','Random Forest','Gradient boosting']}
    predictions = {name: [] for name in fits}

    class Constant:
        def __init__(self, name, value): self.name, self.value = name, value
        def fit(self, X, y): fits[self.name].append(list(X.index)); return self
        def predict(self, X): predictions[self.name].append(list(X.index)); return np.full(len(X), self.value)

    with patch('dashboard.forecast.model_factories', return_value={
        'Ridge regression': lambda: Constant('Ridge regression', np.exp(.007)-1),
        'Random Forest': lambda: Constant('Random Forest', .2),
        'Gradient boosting': lambda: Constant('Gradient boosting', .3)}):
        result = forecast(data, 7)
    assert result['model'] == 'Ridge regression'
    assert fits['Ridge regression'][:3] == fits['Random Forest'] == fits['Gradient boosting']
    assert len(fits['Ridge regression']) == 5
    assert predictions['Ridge regression'][-1] == [len(data)-1]
    assert result['beats_baseline_on_holdout']


def test_ridge_scaler_fits_each_training_window():
    from sklearn.linear_model import Ridge
    original = Ridge.fit
    means = []

    def checked_fit(self, X, y, **kwargs):
        means.append(np.asarray(X).mean(axis=0))
        return original(self, X, y, **kwargs)

    with patch.object(Ridge, 'fit', checked_fit):
        forecast(history(), 7)
    assert len(means) >= 3
    assert all(np.allclose(mean, 0, atol=1e-7) for mean in means)


@pytest.mark.parametrize('horizon',[64,126,252,504])
def test_horizons_beyond_three_months_are_rejected(horizon):
    with pytest.raises(ValueError, match='1 and 63'):
        forecast(history(1260),horizon)


def test_development_winner_failing_recent_check_is_not_refit_or_shown():
    data=history()
    data['Close']=100*np.exp(np.minimum(np.arange(len(data)),420)*.001)
    fits=[]
    class Constant:
        def fit(self,X,y): fits.append(len(X)); return self
        def predict(self,X): return np.full(len(X),np.exp(.007)-1)
    with patch('dashboard.forecast.model_factories',return_value={'Ridge regression':Constant}):
        result=forecast(data,7)
    assert result['model']=='Ridge regression'
    assert not result['available'] and not result['beats_baseline_on_holdout']
    assert 'separate recent test' in result['reason']
    assert len(fits)==4  # Three development folds and the holdout check; no inference refit.
    assert 'predicted_price' not in result and 'predicted_return' not in result
