from unittest.mock import patch
from dashboard.runtime import prepare_runtime
from dashboard import forecast as forecast_module, storage, market
from etl import shared_store
import dashboard


def test_current_runtime_activates_once_without_reload_or_database_requests():
    with patch('dashboard.runtime._active_version', None), \
         patch('dashboard.runtime.importlib.reload') as reload, \
         patch('dashboard.storage._store') as store, \
         patch('dashboard.market.get_history') as history:
        prepare_runtime()
        prepare_runtime()
        reload.assert_not_called()
        store.assert_not_called(); store.clear.assert_called_once()
        history.assert_not_called(); history.clear.assert_called_once()


def test_old_runtime_reloads_dependencies_and_clears_only_memory_caches():
    with patch('dashboard.runtime._active_version', None), \
         patch.object(shared_store, 'RUNTIME_VERSION', 'old'), \
         patch('dashboard.runtime.importlib.reload', side_effect=lambda module: module) as reload, \
         patch('dashboard.storage._store') as store, \
         patch('dashboard.storage._maintenance') as maintenance, \
         patch('dashboard.storage.saved_catalog') as catalog, \
         patch('dashboard.market.get_history') as history, \
         patch('dashboard.market.get_forecast') as forecast:
        prepare_runtime()
        assert [call.args[0] for call in reload.call_args_list] == [shared_store, forecast_module, storage, market]
        for cached in [store, maintenance, catalog, history, forecast]:
            cached.clear.assert_called_once()
            cached.assert_not_called()


def test_streamlit_stale_package_attribute_does_not_trigger_invalid_reload():
    with patch('dashboard.runtime._active_version', None), \
         patch.object(dashboard, 'storage', object()), \
         patch('dashboard.runtime.importlib.reload') as reload:
        prepare_runtime()
        reload.assert_not_called()
