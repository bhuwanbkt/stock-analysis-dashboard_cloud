from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest


def prices():
    rng=np.random.default_rng(42)
    dates=pd.bdate_range('2024-01-01',periods=510)
    values=100*np.exp(np.cumsum(rng.normal(0,.01,len(dates))))
    return pd.DataFrame({'Date':dates,'Open':values,'High':values*1.01,'Low':values*.99,
                         'Close':values,'Volume':rng.integers(100000,200000,len(dates))})


def element(items,label):
    return next(item for item in items if item.label==label)


def test_browsing_custom_ticker_and_button_only_forecast():
    app=Path(__file__).resolve().parents[1]/'dashboard'/'app.py'
    packet={'prices':prices(),'fetched_at':'2026-10-09T23:00:00+00:00'}
    result={'available':True,'predicted_price':100,'predicted_return':0,'model':'Unchanged-price baseline',
            'mae_pct':3,'baseline_mae_pct':3,'test_rows':80,'training_rows':470,'as_of':'2025-12-12'}
    with patch('dashboard.market.get_history',return_value=packet) as download, \
         patch('dashboard.market.get_profile') as profile, \
         patch('dashboard.market.get_forecast',return_value=result) as model, \
         patch('etl.load.load_to_postgres') as db:
        at=AppTest.from_file(str(app)).run(timeout=30)
        assert not at.exception
        assert element(at.selectbox,'Search a company').value=='AAPL'
        profile.assert_not_called();model.assert_not_called();db.assert_not_called()
        element(at.selectbox,'Search a company').set_value('MSFT').run()
        assert not at.exception
        assert any('MSFT' in h.value for h in at.subheader)
        element(at.radio,'View').set_value('Forecast quality').run()
        model.assert_not_called()
        element(at.button,'Run forecast').click().run(timeout=30)
        assert not at.exception
        model.assert_called_once()
        assert any('fallback' in item.value for item in at.info)
        element(at.text_input,'Enter an additional ticker').set_value('cost')
        element(at.button,'Look up ticker').click().run()
        assert not at.exception
        assert element(at.selectbox,'Search a company').value=='COST'
        assert 'COST' in at.session_state['custom_companies']
        assert any(call.args[0]=='COST' for call in download.call_args_list)
        db.assert_not_called()


def test_comparison_button_and_invalid_symbol():
    app=Path(__file__).resolve().parents[1]/'dashboard'/'app.py'
    packet={'prices':prices(),'fetched_at':'2026-10-09T23:00:00+00:00'}
    with patch('dashboard.market.get_history',return_value=packet) as download:
        at=AppTest.from_file(str(app)).run(timeout=30)
        element(at.radio,'View').set_value('Compare').run()
        assert not any(call.args[0]=='MSFT' for call in download.call_args_list)
        element(at.button,'Compare stocks').click().run()
        assert not at.exception
        assert any(call.args[0]=='MSFT' for call in download.call_args_list)
        assert any('Both start at 0%' in caption.value for caption in at.caption)
        before=download.call_count
        element(at.text_input,'Enter an additional ticker').set_value('<script>')
        element(at.button,'Look up ticker').click().run()
        assert not at.exception
        assert any('Enter a ticker' in warning.value for warning in at.warning)
        # Normal browsing runs again, but the invalid value never reaches the provider.
        assert not any(call.args[0]=='<SCRIPT>' for call in download.call_args_list)
