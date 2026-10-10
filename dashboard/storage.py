"""Optional Neon connection and bounded process-local adapters. Never expose credentials."""
import hashlib
import streamlit as st
from dashboard.database_admin import setting


@st.cache_resource
def _store(database_url):
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from etl.shared_store import SharedStore
    # Close idle client connections rather than holding Neon awake between visits.
    url=database_url.replace('postgres://','postgresql://',1)
    engine=create_engine(url,poolclass=NullPool,connect_args={'connect_timeout':5})
    repo=SharedStore(engine)
    repo.initialize()
    return repo


@st.cache_data(ttl=3600,show_spinner=False)
def _maintenance(key, _repo):
    return _repo.maintain()


def get_store():
    url=setting('DATABASE_URL')
    if not url: return None
    try:
        repo=_store(url)
        try: _maintenance(hashlib.sha256(url.encode()).hexdigest(),repo)
        except Exception: pass
        return repo
    except Exception:
        return None


@st.cache_data(ttl=300,max_entries=1,show_spinner=False)
def saved_catalog():
    repo=get_store()
    try: return repo.catalog() if repo else {}
    except Exception: return {}


def remember_company(symbol,profile):
    repo=get_store()
    try:
        if repo and repo.save_profile(symbol,profile): saved_catalog.clear()
    except Exception:
        pass


def forecast_history(symbol):
    repo=get_store()
    try: return repo.forecast_history(symbol) if repo else []
    except Exception: return []
