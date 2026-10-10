"""Deterministic calculations, without an LLM or additional API requests."""
import numpy as np
import pandas as pd

PERIOD_MONTHS = {'1 Month': 1, '3 Months': 3, '6 Months': 6, '1 Year': 12, '2 Years': 24, '5 Years': 60}


def select_period(prices, label):
    cutoff = prices.Date.iloc[-1] - pd.DateOffset(months=PERIOD_MONTHS[label])
    return prices.loc[prices.Date >= cutoff].copy()


def summarize(prices):
    close = prices.Close
    returns = close.pct_change(fill_method=None).dropna()
    drawdown = close / close.cummax() - 1
    ma50 = float(close.tail(50).mean()) if len(close) >= 50 else None
    return {'return_pct': float((close.iloc[-1] / close.iloc[0] - 1) * 100),
            'daily_volatility_pct': float(returns.std() * 100) if len(returns) > 1 else None,
            'max_drawdown_pct': float(drawdown.min() * 100), 'ma50': ma50,
            'ma50_distance_pct': float((close.iloc[-1] / ma50 - 1) * 100) if ma50 else None,
            'rows': len(prices)}


def compare_returns(left, right, left_label, right_label):
    if left_label == right_label:
        raise ValueError('Select two different stocks.')
    joined = left[['Date', 'Close']].merge(right[['Date', 'Close']], on='Date', suffixes=('_left', '_right'))
    joined = joined.sort_values('Date')
    if len(joined) < 2:
        raise ValueError('Not enough shared dates to compare these stocks.')
    result = pd.DataFrame({'Date': joined.Date})
    result[left_label] = (joined.Close_left / joined.Close_left.iloc[0] - 1) * 100
    result[right_label] = (joined.Close_right / joined.Close_right.iloc[0] - 1) * 100
    return result
