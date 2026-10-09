import sys
import os
import streamlit as st

# Page configuration
st.set_page_config(
    page_title="Advanced Stock Analysis Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union



# Add project root to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import ETL functions instead of reimplementing them
try:
    from etl.extract import extract_stock_data
    from etl.transform import add_indicators
    from etl.load import load_to_postgres
except ImportError as e:
    st.error(f"ETL modules not found: {e}")


    # Fallback implementations if ETL modules aren't available
    def extract_stock_data(ticker, period='1y'):
        data = yf.download(ticker, period=period)
        data.reset_index(inplace=True)
        return data


    def add_indicators(df):
        df['MA_10'] = df['Close'].rolling(10).mean()
        df['MA_50'] = df['Close'].rolling(50).mean()
        return df


    def load_to_postgres(df, table_name):
        st.sidebar.info("Database functionality not available")

# Constants
PERIOD_OPTIONS = {
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "1 Year": "1y",
    "2 Years": "2y",
    "5 Years": "5y"
}

from dashboard.catalog import load_catalog, search_catalog
from dashboard.forecast import forecast

COMPANIES = load_catalog()
ALL_TICKERS = {symbol: row['name'] for symbol, row in COMPANIES.items()}
TOP_STOCKS = dict(list(ALL_TICKERS.items())[:10])

# Custom CSS for styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #00C805;
        text-align: center;
        margin-bottom: 1rem;
    }
    .stock-card {
        background-color: #f8f9fa;
        border-radius: 0.5rem;
        padding: 1rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
        transition: transform 0.2s;
    }
    .metric-card {
        background-color: #5e6133;
        border-radius: 0.5rem;
        padding: 1rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        text-align: center;
    }
    .positive-change { color: #00C805; }
    .negative-change { color: #FF5000; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #6cbcf5;
        border-radius: 4px 4px 0px 0px;
        padding: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #00C805;
        color: white;
    }
    .prediction-positive { color: #00C805; font-weight: bold; }
    .prediction-negative { color: #FF5000; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=900, max_entries=32, show_spinner=False)
def download_stock_data(ticker: str, period: str) -> Optional[pd.DataFrame]:
    """Cache stock data downloads to reduce API calls using the ETL extract function"""
    try:
        df = extract_stock_data(ticker, period)
        if df is None or df.empty:
            return None

        # Handle MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df['Date'] = pd.to_datetime(df['Date'])
        return df
    except Exception:
        return None


@st.cache_data(ttl=3600, max_entries=16, show_spinner=False)
def predict_stock_price(df, days_to_predict=7):
    return forecast(df, days_to_predict)


def create_sparkline_chart(data: pd.Series, color: str) -> go.Figure:
    """Create a sparkline chart"""
    fig = go.Figure(go.Scatter(
        x=data.index,
        y=data.values,
        mode='lines',
        line=dict(color=color, width=2)
    ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=60,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )
    return fig


def display_top_stocks():
    """Display top stocks in columns"""
    top_cols = st.columns(5, gap="large")
    for i, (ticker, name) in enumerate(TOP_STOCKS.items()):
        col = top_cols[i % 5]
        try:
            df_top = download_stock_data(ticker, "1mo")
            if df_top is None:
                col.write(f"{ticker}: No data")
                continue

            last_price = df_top['Close'].iloc[-1]
            prev_close = df_top['Close'].iloc[-2] if len(df_top) > 1 else last_price
            pct_change = ((last_price - prev_close) / prev_close) * 100

            spark_fig = create_sparkline_chart(df_top['Close'],
                                               '#00C805' if pct_change >= 0 else '#FF5000')

            delta_color = "normal"
            col.metric(
                label=ticker,
                value=f"${last_price:.2f}",
                delta=f"{pct_change:.2f}%",
                delta_color=delta_color
            )
            col.plotly_chart(spark_fig, use_container_width=True)
            col.caption(name)
        except Exception:
            col.error(f"{ticker} data unavailable")


def main():
    """Main application function"""
    st.markdown('<h1 class="main-header">Advanced Stock Analysis Dashboard</h1>', unsafe_allow_html=True)

    # Sidebar
    st.sidebar.header("Settings")
    selected_period = st.sidebar.selectbox(
        "Select Time Period",
        list(PERIOD_OPTIONS.keys()),
        index=2
    )
    period_value = PERIOD_OPTIONS[selected_period]

    st.sidebar.header("ML Prediction Settings")
    prediction_days = st.sidebar.selectbox("Trading sessions ahead", [1, 5, 7, 10, 20, 30], index=2)
    enable_forecast = st.sidebar.checkbox("Show experimental forecast", value=False)
    st.sidebar.caption("Forecasts use two years of history, independently of the chart period.")

    st.subheader("Search a company")
    search_input = st.text_input("Company name or ticker", placeholder="Apple or AAPL")
    matches = search_catalog(COMPANIES, search_input)
    if not matches:
        st.info("No saved company matches. Try another name or ticker.")
        return
    selected_ticker = st.selectbox("Select stock", matches,
                                   format_func=lambda symbol: f"{COMPANIES[symbol]['name']} ({symbol})")
    profile = COMPANIES[selected_ticker]
    with st.expander("About this company", expanded=True):
        st.write(profile.get('overview') or "Company overview has not been downloaded yet.")
        if profile.get('sector'):
            st.caption(f"Sector: {profile['sector']} · Industry: {profile.get('industry') or 'Unavailable'}")
        st.caption(f"Profile source: {profile['source']} · Updated: {profile.get('updated_at') or 'Pending'}")
    analyze_stock(selected_ticker, period_value, prediction_days, enable_forecast)
    with st.expander("Popular stocks"):
        if st.checkbox("Load popular stock prices", value=False):
            display_top_stocks()


def analyze_stock(ticker: str, period: str, prediction_days: int, enable_forecast: bool):
    """Analyze a single stock"""
    try:
        with st.spinner(f"Loading {ticker} data..."):
            df = download_stock_data(ticker, period)

        if df is None or df.empty:
            st.error(f"Stock '{ticker}' not found")
            return

        # Use the ETL transform function instead of reimplementing it
        df = add_indicators(df)
        latest = df.iloc[-1]

        # Database storage is optional in the zero-cost hosted experience.
        if os.getenv('ENABLE_DATABASE_EXPORT') == '1' and st.sidebar.button("Save prices to database"):
            try:
                if load_to_postgres(df, table_name=ticker.lower()):
                    st.sidebar.success("Prices saved")
                else:
                    st.sidebar.error("Database export is unavailable. Please try again later.")
            except Exception:
                st.sidebar.error("Database export is unavailable. Please try again later.")

        # Display stock analysis
        display_stock_analysis(ticker, df, latest, prediction_days, enable_forecast)

    except Exception as e:
        st.error(f"Error loading data for '{ticker}': {str(e)}")


def display_stock_analysis(ticker: str, df: pd.DataFrame, latest: pd.Series,
                           prediction_days: int, enable_forecast: bool):
    """Display comprehensive stock analysis"""
    # Get latest data
    volume = int(latest['Volume'])
    open_price = latest['Open']
    high_price = latest['High']
    low_price = latest['Low']
    close_price = latest['Close']

    # Get previous close (second to last row)
    if len(df) > 1:
        prev_close = df.iloc[-2]['Close']
    else:
        prev_close = close_price

    price_change = close_price - prev_close
    pct_change = (price_change / prev_close) * 100

    high_52 = df['High'].max()
    low_52 = df['Low'].min()

    # Calculate volatility safely
    if 'Close' in df.columns and len(df) > 10:
        volatility = df['Close'].pct_change().rolling(10).std().iloc[-1]
    else:
        volatility = 0

    # ML Prediction
    result = {'available': False, 'reason': 'Enable the experimental forecast in Settings to run it.'}
    if enable_forecast:
        with st.spinner("Evaluating forecast against historical prices..."):
            history = download_stock_data(ticker, '2y')
            if history is not None:
                try:
                    result = predict_stock_price(history, prediction_days)
                except ValueError as exc:
                    result = {'available': False, 'reason': str(exc)}
            else:
                result = {'available': False, 'reason': 'Forecast history is unavailable. Try again later.'}
    st.caption(f"Yahoo Finance via yfinance · Latest price bar: {latest['Date']} · Downloads cached for 15 minutes. Prices may be delayed and adjusted for corporate actions.")

    # Display metrics
    st.subheader(f"{ticker} - {ALL_TICKERS.get(ticker, 'N/A')} Overview")

    # Main metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Current Price", f"${close_price:.2f}",
                  f"{price_change:.2f} ({pct_change:.2f}%)")
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Open", f"${open_price:.2f}")
        st.metric("Prev Close", f"${prev_close:.2f}")
        st.markdown('</div>', unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("High", f"${high_price:.2f}")
        st.metric("Low", f"${low_price:.2f}")
        st.markdown('</div>', unsafe_allow_html=True)

    with col4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Volume", f"{volume:,}")
        st.metric("10-day Volatility", f"{volatility:.4f}")
        st.markdown('</div>', unsafe_allow_html=True)

    # ML Prediction and 52-week range
    col5, col6 = st.columns(2)

    with col5:
        st.subheader(f"Experimental forecast · {prediction_days} trading sessions")
        if result['available']:
            st.metric("Estimated price", f"${result['predicted_price']:.2f}", f"{result['predicted_return']:.2%}")
            st.caption(f"Selected method: {result['model']} · Based on bar: {result['as_of']}")
        else:
            st.info(result['reason'])

    with col6:
        # 52-week high/low
        if high_52 != low_52:  # Avoid division by zero
            width_percent = ((close_price - low_52) / (high_52 - low_52)) * 100
        else:
            width_percent = 50

        st.markdown(f"""
        <div class="metric-card">
            <h4>Selected Period Range</h4>
            <p>High: ${high_52:.2f} | Low: ${low_52:.2f}</p>
            <div style="background: #e0e0e0; height: 10px; border-radius: 5px; margin: 10px 0;">
                <div style="background: #00C805; height: 100%; border-radius: 5px; width: {width_percent}%;"></div>
            </div>
            <p>Current: ${close_price:.2f}</p>
        </div>
        """, unsafe_allow_html=True)

    # Tabs: Price Charts, Technical Indicators, ML Insights
    tabs = st.tabs(["Price Charts", "Technical Indicators", "ML Insights"])

    # Tab 1: Price Charts
    with tabs[0]:
        col1, col2 = st.columns(2)

        with col1:
            # Line Chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df['Date'],
                y=df['Close'],
                mode='lines',
                name='Close',
                line=dict(color='#00C805', width=2)
            ))

            # Add moving averages if they exist
            if 'MA_10' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['MA_10'],
                    mode='lines',
                    name='10-Day MA',
                    line=dict(color='#FF9900', width=1.5, dash='dash')
                ))

            if 'MA_50' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['MA_50'],
                    mode='lines',
                    name='50-Day MA',
                    line=dict(color='#3366CC', width=1.5, dash='dash')
                ))

            fig.update_layout(
                title=f"{ticker} Price Chart",
                xaxis_title="Date",
                yaxis_title="Price ($)",
                template="plotly_white",
                height=500,
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Candlestick Chart
            fig = go.Figure(data=[go.Candlestick(
                x=df['Date'],
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name="Price",
                increasing_line_color='#00C805',
                decreasing_line_color='#FF5000'
            )])

            fig.update_layout(
                title=f"{ticker} Candlestick Chart",
                xaxis_title="Date",
                yaxis_title="Price ($)",
                template="plotly_white",
                height=500,
                xaxis_rangeslider_visible=False
            )
            st.plotly_chart(fig, use_container_width=True)

    # Tab 2: Technical Indicators
    with tabs[1]:
        col1, col2 = st.columns(2)

        with col1:
            # Moving Averages
            if all(col in df.columns for col in ['MA_10', 'MA_20', 'MA_50']):
                fig_ma = go.Figure()
                fig_ma.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['Close'],
                    mode='lines',
                    name='Close',
                    line=dict(color='#00C805', width=2)
                ))
                fig_ma.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['MA_10'],
                    mode='lines',
                    name='10-Day MA',
                    line=dict(color='#FF9900', width=1.5)
                ))
                fig_ma.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['MA_20'],
                    mode='lines',
                    name='20-Day MA',
                    line=dict(color='#3366CC', width=1.5)
                ))
                fig_ma.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['MA_50'],
                    mode='lines',
                    name='50-Day MA',
                    line=dict(color='#FF00FF', width=1.5)
                ))
                fig_ma.update_layout(
                    title="Moving Averages",
                    xaxis_title="Date",
                    yaxis_title="Price ($)",
                    template="plotly_white",
                    height=400
                )
                st.plotly_chart(fig_ma, use_container_width=True)

            # RSI
            if 'RSI' in df.columns:
                fig_rsi = go.Figure()
                fig_rsi.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['RSI'],
                    mode='lines',
                    name='RSI',
                    line=dict(color='#00C805', width=2)
                ))
                fig_rsi.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Overbought")
                fig_rsi.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Oversold")
                fig_rsi.update_layout(
                    title="RSI (14 periods)",
                    xaxis_title="Date",
                    yaxis_title="RSI",
                    template="plotly_white",
                    height=300,
                    yaxis_range=[0, 100]
                )
                st.plotly_chart(fig_rsi, use_container_width=True)

        with col2:
            # MACD
            if all(col in df.columns for col in ['MACD', 'MACD_Signal', 'MACD_Histogram']):
                fig_macd = go.Figure()
                fig_macd.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['MACD'],
                    mode='lines',
                    name='MACD',
                    line=dict(color='#00C805', width=2)
                ))
                fig_macd.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['MACD_Signal'],
                    mode='lines',
                    name='Signal',
                    line=dict(color='#FF0000', width=2)
                ))

                # Histogram
                colors = np.where(df['MACD_Histogram'] < 0, 'red', 'green')
                fig_macd.add_trace(go.Bar(
                    x=df['Date'],
                    y=df['MACD_Histogram'],
                    name='Histogram',
                    marker_color=colors
                ))

                fig_macd.update_layout(
                    title="MACD",
                    xaxis_title="Date",
                    yaxis_title="MACD",
                    template="plotly_white",
                    height=400
                )
                st.plotly_chart(fig_macd, use_container_width=True)

            # Bollinger Bands
            if all(col in df.columns for col in ['BB_Upper', 'BB_Middle', 'BB_Lower']):
                fig_bb = go.Figure()
                fig_bb.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['Close'],
                    mode='lines',
                    name='Close',
                    line=dict(color='#00C805', width=2)
                ))
                fig_bb.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['BB_Upper'],
                    mode='lines',
                    name='Upper Band',
                    line=dict(color='#FF0000', width=1, dash='dash')
                ))
                fig_bb.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['BB_Middle'],
                    mode='lines',
                    name='Middle Band',
                    line=dict(color='#0000FF', width=1)
                ))
                fig_bb.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['BB_Lower'],
                    mode='lines',
                    name='Lower Band',
                    line=dict(color='#00FF00', width=1, dash='dash')
                ))
                fig_bb.update_layout(
                    title="Bollinger Bands",
                    xaxis_title="Date",
                    yaxis_title="Price ($)",
                    template="plotly_white",
                    height=300
                )
                st.plotly_chart(fig_bb, use_container_width=True)

        # Volume and OBV
        col3, col4 = st.columns(2)
        with col3:
            # Volume chart
            fig_vol = go.Figure()
            fig_vol.add_trace(go.Bar(
                x=df['Date'],
                y=df['Volume'],
                name='Volume',
                marker_color='#1f77b4'
            ))
            fig_vol.update_layout(
                title="Trading Volume",
                xaxis_title="Date",
                yaxis_title="Volume",
                template="plotly_white",
                height=300
            )
            st.plotly_chart(fig_vol, use_container_width=True)

        with col4:
            # OBV chart
            if 'OBV' in df.columns:
                fig_obv = go.Figure()
                fig_obv.add_trace(go.Scatter(
                    x=df['Date'],
                    y=df['OBV'],
                    mode='lines',
                    name='OBV',
                    line=dict(color='#FF9900', width=2)
                ))
                fig_obv.update_layout(
                    title="On-Balance Volume (OBV)",
                    xaxis_title="Date",
                    yaxis_title="OBV",
                    template="plotly_white",
                    height=300
                )
                st.plotly_chart(fig_obv, use_container_width=True)

    # Tab 3: honest endpoint forecast, without invented daily paths or confidence.
    with tabs[2]:
        if result['available']:
            st.subheader("Historical forecast quality")
            c1, c2 = st.columns(2)
            c1.metric("Selected method: average return error", f"{result['mae_pct']:.2f} percentage points")
            c2.metric("Unchanged-price baseline error", f"{result['baseline_mae_pct']:.2f} percentage points")
            st.caption(f"Untouched test: {result['test_rows']} origins from {result['test_start']} to {result['test_end']}. Training: {result['training_rows']} labelled rows.")
            if result['beats_baseline_on_holdout']:
                st.success("Selected method had lower average error than unchanged price on this test period.")
            else:
                st.info("This test does not show an improvement over assuming price stays unchanged.")
            if result['direction_accuracy'] is not None:
                st.write(f"Historical direction accuracy: {result['direction_accuracy']:.1%}")
            st.write("The method is selected on three earlier time-ordered validation windows. A separate latest test window reports its performance. Training labels are kept clear of future test origins.")
            st.caption("One endpoint is predicted. Trading sessions exclude weekends and exchange holidays; no calendar date or daily path is implied. Historical errors are not a confidence probability or a promise of future accuracy.")
            st.caption("Overlapping multi-session targets are correlated; the number of test origins is not the number of independent observations.")
        else:
            st.info(result['reason'])
        st.caption("Experimental analysis for learning, not a trading recommendation.")

    # Display raw data
    with st.expander("View Raw Data"):
        st.dataframe(df.tail(20), use_container_width=True)


if __name__ == "__main__":
    main()
