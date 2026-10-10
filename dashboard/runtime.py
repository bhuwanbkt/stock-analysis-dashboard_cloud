"""Keep imported data adapters current when a multipage app updates without restarting."""
import importlib
import threading

RUNTIME_VERSION = 'five-year-predictions-v1'
_runtime_lock = threading.RLock()


def prepare_runtime():
    with _runtime_lock:
        _prepare_runtime()


def _prepare_runtime():
    from etl import shared_store
    from dashboard import forecast, storage, market
    modules = (shared_store, forecast, storage, market)
    if all(getattr(module, 'RUNTIME_VERSION', None) == RUNTIME_VERSION for module in modules):
        return
    # Reload dependencies first, before running either page. This runs only for an
    # old in-process generation; a normal rerun or cold start needs no reload.
    for module in modules:
        importlib.reload(module)
    storage._store.clear()
    storage._maintenance.clear()
    storage.saved_catalog.clear()
    market.get_history.clear()
    market.get_forecast.clear()
