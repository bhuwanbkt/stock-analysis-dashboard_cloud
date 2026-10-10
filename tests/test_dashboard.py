from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from streamlit.runtime.pages_manager import PagesManager


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


def test_company_name_search_requires_buttons_and_opens_listing():
    app=Path(__file__).resolve().parents[1]/'dashboard'/'app.py'
    packet={'prices':prices(),'fetched_at':'2026-10-09T23:00:00+00:00'}
    sony={'symbol':'SONY','name':'Sony Group Corporation','exchange':'NYSE',
          'overview':None,'currency':None,'source':'Yahoo Finance search','updated_at':None}
    with patch('dashboard.market.get_history',return_value=packet) as history, \
         patch('dashboard.market.get_company_matches',return_value=[sony]) as search, \
         patch('etl.load.load_to_postgres') as db:
        at=AppTest.from_file(str(app)).run(timeout=30)
        element(at.text_input,'Search provider by company name').set_value('Sony').run()
        search.assert_not_called()
        element(at.button,'Find companies').click().run()
        assert not at.exception
        search.assert_called_once_with('sony')
        assert element(at.selectbox,'Choose a company listing').value=='SONY'
        assert not any(call.args[0]=='SONY' for call in history.call_args_list)
        element(at.button,'Open selected company').click().run()
        assert not at.exception
        assert element(at.selectbox,'Search a company').value=='SONY'
        assert any('Sony Group Corporation' in h.value for h in at.subheader)
        db.assert_not_called()


def test_company_url_restores_selection_after_restart():
    app=Path(__file__).resolve().parents[1]/'dashboard'/'app.py'
    packet={'prices':prices(),'fetched_at':'2026-10-09T23:00:00+00:00','source':'Postgres','persisted':True}
    with patch('dashboard.market.get_history',return_value=packet),patch('dashboard.storage.saved_catalog',return_value={}):
        at=AppTest.from_file(str(app))
        at.query_params['symbol']='SONY'
        at.run(timeout=30)
        assert not at.exception
        assert element(at.selectbox,'Search a company').value=='SONY'
        assert at.query_params['symbol']==['SONY']
        assert any('Saved in shared Postgres' in item.value for item in at.caption)


def test_admin_button_opens_separate_page_and_returns_to_selected_stock():
    app=Path(__file__).resolve().parents[1]/'dashboard'/'app.py'
    packet={'prices':prices(),'fetched_at':'2026-10-09T23:00:00+00:00'}
    with patch('dashboard.market.get_history',return_value=packet) as history, \
         patch('dashboard.storage.saved_catalog',return_value={}), \
         patch('dashboard.database_admin.setting',return_value=''), \
         patch('etl.cleanup.list_price_tables') as listing, \
         patch.object(PagesManager, 'uses_pages_directory', False):
        at=AppTest.from_file(str(app)).run(timeout=30)
        assert not at.exception
        assert not any(row.label=='Delete saved database data' for row in at.expander)
        element(at.selectbox,'Search a company').set_value('MSFT').run()
        before=history.call_count
        assert at.sidebar.button[0].label=='Open admin page'
        assert not any(row.label=='Open admin page' for row in at.main.button)
        element(at.sidebar.button,'Open admin page').click().run()
        assert not at.exception
        assert any(row.value=='Database administration' for row in at.title)
        assert not any(row.label=='Search a company' for row in at.selectbox)
        assert history.call_count==before
        listing.assert_not_called()
        element(at.button,'Back to Stock Explorer').click().run(timeout=30)
        assert not at.exception
        assert element(at.selectbox,'Search a company').value=='MSFT'


def test_direct_admin_page_is_password_protected_and_does_not_load_prices():
    app=Path(__file__).resolve().parents[1]/'dashboard'/'app.py'
    settings={'DATABASE_URL':'postgresql://placeholder','DATABASE_ADMIN_TOKEN':'test-only-password-over-24-characters'}
    with patch('dashboard.database_admin.setting',side_effect=lambda key:settings.get(key,'')), \
         patch('dashboard.market.get_history') as history, \
         patch('etl.cleanup.list_price_tables') as listing, \
         patch('etl.cleanup.delete_price_rows') as delete, \
         patch.object(PagesManager, 'uses_pages_directory', False):
        at=AppTest.from_file(str(app)).switch_page('pages/admin.py').run(timeout=30)
        assert not at.exception
        assert any(row.value=='Database administration' for row in at.title)
        assert element(at.text_input,'Database administrator password').proto.type==1
        history.assert_not_called();listing.assert_not_called();delete.assert_not_called()


def test_admin_storage_overview_is_explicit_and_does_not_download():
    app=Path(__file__).resolve().parents[1]/'dashboard'/'app.py'
    settings={'DATABASE_URL':'postgresql://placeholder','DATABASE_ADMIN_TOKEN':'test-only-password-over-24-characters'}
    summary={'companies':2,'prices':1000,'forecasts':3,'company_limit':50,'forecast_limit':5000,
             'database_bytes':1048576,'last_cleanup':None,'last_refresh':None}
    with patch('dashboard.database_admin.setting',side_effect=lambda key:settings.get(key,'')), \
         patch('dashboard.database_admin.authorized',return_value=True), \
         patch('dashboard.storage._store') as store, \
         patch('dashboard.market.get_history') as history, \
         patch('etl.cleanup.list_price_tables') as listing:
        store.return_value.storage_summary.return_value=summary
        at=AppTest.from_file(str(app)).switch_page('pages/admin.py').run(timeout=30)
        assert not at.exception
        store.assert_not_called()
        element(at.button,'Refresh storage overview').click().run()
        assert not at.exception
        assert any(row.label=='Saved companies' and row.value=='2 / 50' for row in at.metric)
        assert any('1.00 MiB' in row.value for row in at.caption)
        store.return_value.storage_summary.assert_called_once()
        history.assert_not_called();listing.assert_not_called()
