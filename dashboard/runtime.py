"""Keep imported data adapters current when a multipage app updates without restarting."""
import importlib
import threading

RUNTIME_VERSION = 'five-year-predictions-v1'
_runtime_lock = threading.RLock()


def prepare_runtime():
    with _runtime_lock:
        _prepare_runtime()


def _prepare_runtime():
    # Streamlit can remove modules from sys.modules while leaving stale package
    # attributes behind. Resolve canonical imports rather than those attributes.
    names = ('etl.shared_store', 'dashboard.forecast', 'dashboard.storage', 'dashboard.market')
    modules = tuple(importlib.import_module(name) for name in names)
    if all(getattr(module, 'RUNTIME_VERSION', None) == RUNTIME_VERSION for module in modules):
        return
    # Reload dependencies first, before running either page. This runs only for an
    # old in-process generation; a normal rerun or cold start needs no reload.
    for name in names:
        importlib.reload(importlib.import_module(name))
    storage = importlib.import_module('dashboard.storage')
    market = importlib.import_module('dashboard.market')
    storage._store.clear()
    storage._maintenance.clear()
    storage.saved_catalog.clear()
    market.get_history.clear()
    market.get_forecast.clear()
