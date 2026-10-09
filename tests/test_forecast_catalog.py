import json
import numpy as np
import pandas as pd
import pytest
from dashboard.forecast import forecast, prepare_features
from dashboard.catalog import load_catalog, search_catalog
from scripts.refresh_companies import refresh


def history(n=510):
    rng = np.random.default_rng(42)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n)))
    return pd.DataFrame({'Date': pd.bdate_range('2023-01-01', periods=n), 'Close': close,
                         'Volume': rng.integers(100000, 200000, n)})


@pytest.mark.parametrize('horizon', [1, 7, 30])
def test_forecast_no_label_leakage_and_latest_inference(horizon):
    data = history()
    result = forecast(data, horizon)
    assert result['available']
    assert result['train_last_origin'] + horizon < result['test_first_origin']
    for fold in result['fold_ranges']:
        assert fold['train_last'] + horizon < fold['valid_first']
    assert result['latest_feature_origin'] == len(data) - 1
    assert result['as_of'] == str(data.Date.iloc[-1])
    assert np.isfinite(result['predicted_price'])
    assert result['predicted_price'] > 0
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
    assert result['predicted_price'] == 100.0
    assert result['mae_pct'] == 0.0
    assert result['direction_accuracy'] is None
