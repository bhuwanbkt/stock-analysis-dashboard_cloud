from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest
from dashboard.market import get_history, get_forecast, clean_prices, normalize_symbol, network_slot, model_slot, MarketUnavailable, ForecastBusy
from dashboard.analysis import summarize, compare_returns, select_period


def sample():
    values=np.array([100.,120.,90.,110.])
    return pd.DataFrame({'Date':pd.bdate_range('2025-01-01',periods=4),'Open':values,'High':values+1,
                         'Low':values-1,'Close':values,'Volume':[10,20,30,40]})


@pytest.mark.parametrize('raw,expected',[(' aapl ','AAPL'),('brk-b','BRK-B'),('^gspc','^GSPC')])
def test_symbols(raw,expected):
    assert normalize_symbol(raw)==expected


def test_bad_symbol_and_price_rows():
    with pytest.raises(ValueError):normalize_symbol('hello world')
    frame=sample();frame.loc[0,'Close']=np.inf
    cleaned=clean_prices(frame)
    assert len(cleaned)==3
    with pytest.raises(MarketUnavailable):clean_prices(pd.DataFrame())


def test_history_is_shared_and_returns_mutation_safe_copies():
    get_history.clear()
    with patch('dashboard.market.yf.Ticker') as ticker:
        ticker.return_value.history.return_value=sample().set_index('Date')
        first=get_history('AAPL')
        first['prices'].loc[0,'Close']=999
        second=get_history('AAPL')
        assert second['prices'].Close.iloc[0]==100
        ticker.return_value.history.assert_called_once()
        kwargs=ticker.return_value.history.call_args.kwargs
        assert kwargs['timeout']==12 and kwargs['raise_errors'] and kwargs['auto_adjust']
    get_history.clear()


def test_failures_not_cached_and_busy_network_avoids_api():
    get_history.clear()
    with patch('dashboard.market.yf.Ticker') as ticker:
        ticker.return_value.history.side_effect=RuntimeError('private provider detail')
        with pytest.raises(MarketUnavailable,match='temporarily unavailable'):get_history('FAIL')
        ticker.return_value.history.side_effect=None
        ticker.return_value.history.return_value=sample().set_index('Date')
        assert len(get_history('FAIL')['prices'])==4
        assert ticker.return_value.history.call_count==2
        slot=network_slot();assert slot.acquire(blocking=False)
        try:
            with pytest.raises(MarketUnavailable,match='Another'):get_history('BUSY')
        finally:slot.release()
    get_history.clear()


def test_forecast_busy_and_released_after_error():
    get_forecast.clear()
    slot=model_slot();assert slot.acquire(blocking=False)
    try:
        with pytest.raises(ForecastBusy):get_forecast('AAPL',sample(),7)
    finally:slot.release()
    with patch('dashboard.forecast.forecast',side_effect=ValueError('bad features')):
        with pytest.raises(ValueError):get_forecast('AAPL',sample(),7)
    assert slot.acquire(blocking=False);slot.release()


def test_summary_and_comparison_alignment():
    left=sample();stats=summarize(left)
    assert stats['return_pct']==pytest.approx(10)
    assert stats['max_drawdown_pct']==pytest.approx(-25)
    right=left.iloc[1:].copy();right['Close']*=2
    result=compare_returns(left,right,'AAPL','MSFT')
    assert result.Date.iloc[0]==left.Date.iloc[1]
    assert result.AAPL.iloc[0]==0 and result.MSFT.iloc[0]==0
    assert result.AAPL.iloc[-1]==pytest.approx(result.MSFT.iloc[-1])
    with pytest.raises(ValueError):compare_returns(left,right,'AAPL','AAPL')
    assert len(select_period(left,'1 Month'))==4


def test_daily_dates_preserve_exchange_session_date():
    raw=sample().set_index('Date')
    raw.index=raw.index.tz_localize('Asia/Tokyo')
    result=clean_prices(raw)
    assert result.Date.iloc[0]==pd.Timestamp('2025-01-01')
    assert result.Date.dt.hour.eq(0).all()
