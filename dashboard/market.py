"""Bounded memory caches backed by optional shared Postgres storage."""
from datetime import datetime, timezone
import re
import threading
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from dashboard.storage import get_store

SYMBOL_RE = re.compile(r'^[A-Z0-9][A-Z0-9.\-^=]{0,14}$|^\^[A-Z0-9.\-]{1,14}$')


class MarketUnavailable(RuntimeError):
    pass


class ForecastBusy(RuntimeError):
    pass


def normalize_symbol(value):
    symbol = value.strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError('Enter a ticker of up to 15 letters, numbers, dots or dashes, such as AAPL or BRK-B.')
    return symbol


@st.cache_resource
def network_slot():
    # yfinance's pinned downloader shares internal state; serialize network calls.
    return threading.BoundedSemaphore(1)


@st.cache_resource
def model_slot():
    return threading.BoundedSemaphore(1)


def clean_prices(raw):
    if raw is None or raw.empty:
        raise MarketUnavailable('No price data returned. Check the ticker or try later; the provider may be unavailable.')
    frame = raw.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    if 'Date' not in frame:
        frame = frame.reset_index().rename(columns={'index': 'Date', 'Datetime': 'Date'})
    required = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    if not set(required).issubset(frame):
        raise MarketUnavailable('The provider returned incomplete price data. Try again later.')
    frame = frame[required].copy()
    # Daily bars are indexed by the exchange's session date, not by UTC midnight.
    frame['Date'] = pd.to_datetime(frame['Date'], errors='coerce').dt.tz_localize(None).dt.normalize()
    for col in required[1:]:
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    frame = frame[(frame[['Open', 'High', 'Low', 'Close']] > 0).all(axis=1) & (frame.Volume >= 0)]
    frame = frame.sort_values('Date').drop_duplicates('Date').reset_index(drop=True)
    if len(frame) < 2:
        raise MarketUnavailable('Not enough valid daily prices were returned. Try another ticker or retry later.')
    return frame


def stale_packet(packet, reason):
    return {**packet, 'stale': True, 'notice': reason}


@st.cache_data(ttl=14400, max_entries=48, show_spinner=False)
def get_history(symbol, period='2y'):
    symbol = normalize_symbol(symbol)
    if period not in ('2y', '5y'):
        raise ValueError('Only bounded two-year and five-year downloads are supported.')
    repo = get_store() if period == '2y' else None
    saved, token, claim = None, None, None
    try:
        if repo:
            saved = repo.read_history(symbol)
            if saved and len(saved['prices']) >= 2 and not saved['stale']:
                return saved
            claim, token = repo.claim_refresh(symbol)
            if claim == 'fresh':
                fresh = repo.read_history(symbol)
                if fresh and len(fresh['prices']) >= 2: return fresh
                raise MarketUnavailable('Saved history changed. Please retry in a moment.')
            if claim in ('busy', 'backoff'):
                if saved and len(saved['prices']) >= 2:
                    return stale_packet(saved, 'Showing saved prices while a refresh is running or waiting to retry.')
                raise MarketUnavailable('A refresh is running or temporarily waiting to retry. Please try again in a few minutes.')
    except MarketUnavailable:
        raise
    except Exception:
        repo = None
    def failed():
        if repo and token:
            try: repo.fail_refresh(symbol, token)
            except Exception: pass
    slot = network_slot()
    if not slot.acquire(blocking=False):
        failed()
        if saved: return stale_packet(saved, 'Another download is running. Showing saved prices.')
        raise MarketUnavailable('Another market-data request is running. Please retry in a moment.')
    try:
        raw = yf.Ticker(symbol).history(period=period, interval='1d', auto_adjust=True,
                                        timeout=12, raise_errors=True)
        frame = clean_prices(raw)
        packet = {'prices': frame, 'downloaded_rows': len(raw) if raw is not None else 0,
                  'period': period, 'fetched_at': datetime.now(timezone.utc).isoformat(),
                  'source': 'API', 'persisted': False, 'stale': False}
        if repo and token:
            try:
                packet['persisted'] = repo.finish_refresh(symbol, frame, packet['downloaded_rows'], token)
                if not packet['persisted']: packet['notice'] = 'Prices are available in memory; this refresh was not saved.'
            except Exception:
                failed()
                packet['notice'] = 'Database save unavailable. Prices are available in memory.'
        elif claim == 'capacity':
            packet['notice'] = 'Shared storage is at its company limit. This stock is available in memory only.'
        elif period == '5y':
            packet['notice'] = 'Five-year history is kept in memory only.'
        else:
            packet['notice'] = 'Shared storage is unavailable or unconfigured. Prices are available in memory only.'
        return packet
    except Exception as exc:
        failed()
        if saved and len(saved['prices']) >= 2:
            return stale_packet(saved, 'The provider could not refresh prices. Showing the saved history and its last download time.')
        if isinstance(exc, MarketUnavailable): raise
        raise MarketUnavailable('Market data is temporarily unavailable or this ticker has no history. Please try later.') from exc
    finally:
        slot.release()


@st.cache_data(ttl=86400, max_entries=24, show_spinner=False)
def get_forecast(symbol, prices, horizon, model_version='three-model-shared-v2'):
    from dashboard.forecast import forecast
    slot = model_slot()
    if not slot.acquire(blocking=False):
        raise ForecastBusy('Another forecast is running. Please retry in a moment.')
    try:
        # Limit model input even when the chart downloads five years.
        cutoff = prices.Date.iloc[-1] - pd.DateOffset(years=2)
        result = forecast(prices.loc[prices.Date >= cutoff].copy(), horizon)
        repo = get_store()
        result['tracking_saved'] = False
        if repo and result.get('available'):
            try: result['tracking_saved'] = repo.record_forecast(symbol, result, model_version)
            except Exception: pass
        return result
    finally:
        slot.release()


@st.cache_data(ttl=86400, max_entries=48, show_spinner=False)
def get_profile(symbol):
    symbol = normalize_symbol(symbol)
    repo, saved = get_store(), None
    try:
        saved = repo.read_profile(symbol) if repo else None
        if saved and saved.get('overview') and not saved['profile_stale']: return saved
    except Exception: repo = None
    slot = network_slot()
    if not slot.acquire(blocking=False):
        raise MarketUnavailable('Another data request is running. Please retry in a moment.')
    try:
        info = yf.Ticker(symbol).get_info()
        if not info.get('longName') or not info.get('longBusinessSummary'):
            raise MarketUnavailable('A complete company overview is not available. Price analysis still works.')
        profile = {'symbol': symbol, 'name': str(info['longName']),
                'overview': str(info['longBusinessSummary']), 'sector': info.get('sector'),
                'industry': info.get('industry'), 'currency': info.get('currency'),
                'source': 'Yahoo Finance via yfinance',
                'updated_at': datetime.now(timezone.utc).isoformat()}
        if repo:
            try: repo.save_profile(symbol, profile)
            except Exception: pass
        return profile
    except MarketUnavailable:
        if saved and saved.get('overview'): return {**saved, 'profile_stale': True}
        raise
    except Exception as exc:
        if saved and saved.get('overview'): return {**saved, 'profile_stale': True}
        raise MarketUnavailable('Company overview is temporarily unavailable. Price analysis still works.') from exc
    finally:
        slot.release()


@st.cache_data(ttl=86400, max_entries=48, show_spinner=False)
def get_company_matches(query):
    query = ' '.join(query.strip().split())
    if not 2 <= len(query) <= 60:
        raise ValueError('Enter a company name or ticker with 2–60 characters.')
    slot = network_slot()
    if not slot.acquire(blocking=False):
        raise MarketUnavailable('Another data request is running. Please retry in a moment.')
    try:
        quotes = yf.Search(query, max_results=8, news_count=0, lists_count=0,
                           recommended=0, include_cb=False, timeout=12).quotes
        matches = {}
        for quote in quotes[:8]:
            if quote.get('quoteType') != 'EQUITY':
                continue
            try:
                symbol = normalize_symbol(quote.get('symbol', ''))
            except ValueError:
                continue
            name = quote.get('longname') or quote.get('shortname')
            if not name:
                continue
            matches[symbol] = {'symbol': symbol, 'name': str(name),
                               'exchange': str(quote.get('exchDisp') or quote.get('exchange') or 'Exchange unavailable'),
                               'overview': None, 'currency': None,
                               'source': 'Yahoo Finance search', 'updated_at': None}
        return list(matches.values())
    except Exception as exc:
        raise MarketUnavailable('Company search is temporarily unavailable. You can still try a known ticker below.') from exc
    finally:
        slot.release()
