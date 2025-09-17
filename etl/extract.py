import yfinance as yf
import pandas as pd
from typing import Optional


def extract_stock_data(ticker: str, period: str = '1y') -> Optional[pd.DataFrame]:
    """
    Extract stock data using yfinance with proper error handling
    """
    try:
        data = yf.download(ticker, period=period)
        if data.empty:
            return data  # Return empty DataFrame instead of None

        data.reset_index(inplace=True)
        # Rename the index column to 'Date' for consistency
        if 'index' in data.columns:
            data.rename(columns={'index': 'Date'}, inplace=True)
        return data
    except Exception:
        return None  # Return None only on exception