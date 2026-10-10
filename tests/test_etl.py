import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from datetime import datetime

# Import ETL functions
from etl.extract import extract_stock_data
from etl.transform import add_indicators, calculate_rsi
from etl.load import load_to_postgres, create_database


class TestExtract:
    """Test cases for extract.py"""

    @patch('etl.extract.yf.download')
    def test_extract_stock_data_success(self, mock_download):
        """Test successful stock data extraction"""
        # Mock response data - yfinance returns DataFrames with Date as index
        mock_data = pd.DataFrame({
            'Open': [150, 151],
            'High': [152, 153],
            'Low': [149, 150],
            'Close': [151, 152],
            'Volume': [1000000, 1200000]
        }, index=pd.to_datetime(['2023-01-01', '2023-01-02']))

        mock_download.return_value = mock_data

        # Call the function
        result = extract_stock_data('AAPL', '1mo')

        # Assertions - the function should rename 'index' to 'Date'
        assert isinstance(result, pd.DataFrame)
        assert 'Date' in result.columns  # Should be renamed to 'Date'
        assert len(result) == 2
        mock_download.assert_called_once_with('AAPL', period='1mo')

    @patch('etl.extract.yf.download')
    def test_extract_stock_data_empty(self, mock_download):
        """Test extraction with empty data"""
        # Empty DataFrame with proper structure
        mock_download.return_value = pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

        result = extract_stock_data('INVALID', '1mo')

        # Should return the empty DataFrame, not None
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch('etl.extract.yf.download')
    def test_extract_stock_data_exception(self, mock_download):
        """Test extraction with exception"""
        mock_download.side_effect = Exception("API error")

        # Should return None on exception
        result = extract_stock_data('AAPL', '1mo')

        assert result is None


class TestTransform:
    """Test cases for transform.py"""

    def test_calculate_rsi(self):
        """Test RSI calculation"""
        prices = pd.Series([100, 102, 101, 103, 105, 104, 106, 107, 108, 109, 110, 111, 112, 113, 114])
        rsi = calculate_rsi(prices, window=14)

        assert isinstance(rsi, pd.Series)
        # RSI should be between 0 and 100
        assert rsi.iloc[-1] >= 0
        assert rsi.iloc[-1] <= 100

    def test_add_indicators_complete_data(self):
        """Test adding indicators with complete data"""
        # Create enough data for indicators to work
        dates = pd.date_range('2023-01-01', periods=50, freq='D')
        df = pd.DataFrame({
            'Date': dates,  # This is what extract() produces after renaming
            'Open': np.random.uniform(100, 110, 50),
            'High': np.random.uniform(110, 120, 50),
            'Low': np.random.uniform(90, 100, 50),
            'Close': np.random.uniform(100, 110, 50),
            'Volume': np.random.randint(1000000, 2000000, 50)
        })

        result = add_indicators(df)

        # Check that indicators were added
        assert 'MA_10' in result.columns
        assert 'RSI' in result.columns
        assert 'MACD' in result.columns
        assert 'BB_Upper' in result.columns
        assert isinstance(result, pd.DataFrame)

    def test_add_indicators_missing_columns(self):
        """Test adding indicators with missing required columns"""
        df = pd.DataFrame({'Close': [100, 101, 102]})  # Missing other required columns

        # Should return the original DataFrame when required columns are missing
        result = add_indicators(df)

        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) == 1  # Only Close column

    def test_add_indicators_empty_data(self):
        """Test adding indicators with empty DataFrame"""
        df = pd.DataFrame()

        # Should return empty DataFrame
        result = add_indicators(df)

        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestLoad:
    """Test cases for load.py"""

    @patch('etl.load.create_engine')
    def test_create_database_exists(self, mock_create_engine):
        """Test database creation when it already exists"""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = [1]  # Database exists
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        create_database()

        mock_conn.execute.assert_called()
        # Should not attempt to create database

    @patch('etl.load.create_engine')
    def test_connection_check_does_not_create_database(self, mock_create_engine):
        """Test database creation when it doesn't exist"""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None  # Database doesn't exist
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        create_database()

        # Cloud loader checks a connection; it does not create a Neon database.
        assert mock_conn.execute.call_count == 1

    @patch('etl.load.create_engine')
    @patch('etl.load.create_database')
    def test_load_to_postgres(self, mock_create_db, mock_create_engine):
        """Test loading data to PostgreSQL"""
        # Create test data
        df = pd.DataFrame({
            'Date': [datetime(2023, 1, 1), datetime(2023, 1, 2)],  # Use 'Date' as extract() produces
            'Close': [100, 101],
            'Volume': [1000000, 1200000]
        })

        # Mock the engine and connection
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        # Mock the to_sql method on the DataFrame
        with patch.object(df, 'to_sql') as mock_to_sql:
            load_to_postgres(df, 'test_table')

            # Verify database operations
            mock_create_db.assert_not_called()
            mock_create_engine.assert_called_once()
            mock_to_sql.assert_called_once_with('test_table', mock_engine, if_exists='replace', index=False)


class TestIntegration:
    """Integration tests for the complete ETL pipeline"""

    @patch('etl.extract.yf.download')
    def test_complete_etl_pipeline(self, mock_download):
        """Test complete ETL pipeline with mocked extraction"""
        # Mock extraction - create enough data for indicators
        dates = pd.date_range('2023-01-01', periods=50, freq='D')
        mock_data = pd.DataFrame({
            'Open': np.random.uniform(100, 110, 50),
            'High': np.random.uniform(110, 120, 50),
            'Low': np.random.uniform(90, 100, 50),
            'Close': np.random.uniform(100, 110, 50),
            'Volume': np.random.randint(1000000, 2000000, 50)
        }, index=dates)
        mock_download.return_value = mock_data

        # Extract
        extracted_data = extract_stock_data('AAPL', '1w')
        assert extracted_data is not None
        assert 'Date' in extracted_data.columns  # Should be renamed to 'Date'

        # Transform
        transformed_data = add_indicators(extracted_data)
        assert transformed_data is not None
        assert 'MA_10' in transformed_data.columns
        assert 'RSI' in transformed_data.columns

        # Load (mock the database operations)
        with patch('etl.load.create_database'), \
                patch('etl.load.create_engine'), \
                patch.object(transformed_data, 'to_sql') as mock_to_sql:
            load_to_postgres(transformed_data, 'test_aapl')
            mock_to_sql.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
