"""Exercise the app without market network calls or a database."""
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest


def test_search_profile_and_forecast_flow():
    rng = np.random.default_rng(42)
    dates = pd.bdate_range('2023-01-01', periods=510)
    price = 100 * np.exp(np.cumsum(rng.normal(0, .01, len(dates))))
    data = pd.DataFrame({'Date': dates, 'Open': price, 'Close': price,
                         'High': price * 1.01, 'Low': price * .99,
                         'Volume': rng.integers(100000, 200000, len(dates))})
    app = Path(__file__).resolve().parents[1] / 'dashboard' / 'app.py'
    with patch('etl.extract.extract_stock_data', return_value=data), patch('etl.load.load_to_postgres') as db:
        at = AppTest.from_file(str(app)).run(timeout=30)
        assert not at.exception
        assert next(box for box in at.selectbox if box.label == 'Select stock').value == 'AAPL'
        at.text_input[0].set_value('Microsoft').run()
        assert not at.exception
        assert next(box for box in at.selectbox if box.label == 'Select stock').value == 'MSFT'
        next(box for box in at.checkbox if box.label == 'Show experimental forecast').check().run(timeout=30)
        assert not at.exception
        assert any('Estimated price' == metric.label for metric in at.metric)
        at.text_input[0].set_value('unmatched company').run()
        assert not at.exception
        assert any('No saved company' in info.value for info in at.info)
        db.assert_not_called()
