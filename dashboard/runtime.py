"""Keep imported data adapters current when a multipage app updates without restarting."""
import importlib
import threading

RUNTIME_VERSION = 'five-year-predictions-v1'
_runtime_lock = threading.RLock()
_active_version = None


def prepare_runtime():
    global _active_version
    with _runtime_lock:
        if _active_version == RUNTIME_VERSION:
            return
        _prepare_runtime()
        _active_version = RUNTIME_VERSION


def _prepare_runtime():
    # Streamlit can remove modules from sys.modules while leaving stale package
    # attributes behind. Resolve canonical imports rather than those attributes.
    names = ('etl.shared_store', 'dashboard.forecast', 'dashboard.storage', 'dashboard.market')
    modules = tuple(importlib.import_module(name) for name in names)
    # Reload dependencies first, before running either page. This runs only for an
    # old in-process generation; a normal rerun or cold start needs no reload.
    if any(getattr(module, 'RUNTIME_VERSION', None) != RUNTIME_VERSION for module in modules):
        for name in names:
            importlib.reload(importlib.import_module(name))
    storage = importlib.import_module('dashboard.storage')
    market = importlib.import_module('dashboard.market')
    # A fresh module can still inherit an older Streamlit cache namespace. Clear
    # once on generation activation even if all imported modules already match.
    storage._store.clear()
    storage._maintenance.clear()
    storage.saved_catalog.clear()
    market.get_history.clear()
    market.get_forecast.clear()
