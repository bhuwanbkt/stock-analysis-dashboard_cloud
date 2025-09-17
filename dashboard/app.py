# dashboard/app.py
import streamlit as st

# Set page configuration MUST be the FIRST Streamlit command
st.set_page_config(
    page_title="Advanced Stock Analysis Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Now import other modules AFTER set_page_config
import sys
import os
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import warnings
from functools import lru_cache
from typing import Dict, List, Tuple, Optional, Union

warnings.filterwarnings('ignore')

# Add project root to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import ETL functions
try:
    from etl.extract import extract_stock_data
    from etl.transform import add_indicators
    from etl.load import load_to_postgres, fetch_from_postgres, create_database
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
        return True


    def fetch_from_postgres(table_name):
        return None


    def create_database():
        return True

# Constants
PERIOD_OPTIONS = {
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "1 Year": "1y",
    "2 Years": "2y",
    "5 Years": "5y"
}

TOP_STOCKS = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corp.",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com Inc.",
    "TSLA": "Tesla Inc.",
    "META": "Meta Platforms Inc.",
    "NVDA": "Nvidia Corp.",
    "NFLX": "Netflix Inc.",
    "INTC": "Intel Corp.",
    "AMD": "Advanced Micro Devices"
}

ADDITIONAL_STOCKS = {
    "PLTR": "Palantir Technologies",
    "UBER": "Uber Technologies",
    "JPM": "JPMorgan Chase",
    "V": "Visa Inc.",
    "DIS": "Walt Disney Co.",
    "PYPL": "PayPal Holdings",
    "GS": "Goldman Sachs",
    "BA": "Boeing Co.",
    "XOM": "Exxon Mobil",
    "JNJ": "Johnson & Johnson"
}

ALL_TICKERS = {**TOP_STOCKS, **ADDITIONAL_STOCKS}

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


@lru_cache(maxsize=32)
def download_stock_data(ticker: str, period: str) -> Optional[pd.DataFrame]:
    """Cache stock data downloads to reduce API calls using the ETL extract function"""
    try:
        df = extract_stock_data(ticker, period)
        if df.empty:
            return None

        # Handle MultiIndex columns by using the first level only
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df['Date'] = pd.to_datetime(df['Date'])
        return df
    except Exception:
        return None


def prepare_ml_data(df: pd.DataFrame, days_to_predict: int = 7) -> Optional[Tuple[pd.DataFrame, List[str]]]:
    """Prepare data for machine learning"""
    df_ml = df.copy()

    # Create features
    df_ml['Price_Change'] = df_ml['Close'].pct_change()
    df_ml['Volume_Change'] = df_ml['Volume'].pct_change()

    # Create lag features
    for lag in range(1, 6):
        df_ml[f'Close_Lag_{lag}'] = df_ml['Close'].shift(lag)
        df_ml[f'Volume_Lag_{lag}'] = df_ml['Volume'].shift(lag)

    # Create target
    df_ml['Future_Close'] = df_ml['Close'].shift(-days_to_predict)
    df_ml = df_ml.dropna()

    if len(df_ml) < 50:
        return None, None

    # Feature columns
    feature_columns = ['Close', 'Volume', 'Price_Change', 'Volume_Change']
    feature_columns.extend([f'Close_Lag_{i}' for i in range(1, 6)])
    feature_columns.extend([f'Volume_Lag_{i}' for i in range(1, 6)])

    # Add technical indicators
    tech_indicators = ['MA_10', 'MA_20', 'MA_50', 'RSI', 'MACD', 'ATR', 'OBV']
    for indicator in tech_indicators:
        if indicator in df_ml.columns:
            feature_columns.append(indicator)

    return df_ml, feature_columns


def predict_stock_price(df: pd.DataFrame, days_to_predict: int = 7) -> Tuple[
    Optional[float], Optional[float], Optional[float]]:
    """Predict stock price using Random Forest"""
    try:
        result = prepare_ml_data(df, days_to_predict)
        if result is None:
            return None, None, None

        df_ml, feature_columns = result

        X = df_ml[feature_columns]
        y = df_ml['Future_Close']

        # Split and scale
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train model
        model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        model.fit(X_train_scaled, y_train)

        # Predict
        train_score = model.score(X_train_scaled, y_train)
        test_score = model.score(X_test_scaled, y_test)

        last_data = df_ml.iloc[-1][feature_columns].values.reshape(1, -1)
        last_data_scaled = scaler.transform(last_data)
        predicted_price = model.predict(last_data_scaled)[0]

        confidence = min(0.95, max(0.5, test_score * 1.2))
        return predicted_price, confidence, test_score

    except Exception as e:
        print(f"Error in ML prediction: {e}")
        return None, None, None


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

            delta_color = "normal" if pct_change >= 0 else "inverse"
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


def display_stock_analysis(ticker: str, df: pd.DataFrame, latest: pd.Series,
                           prediction_days: int, confidence_threshold: float):
    """Display comprehensive stock analysis"""
    # Get latest data
    volume_val = latest['Volume']
    if hasattr(volume_val, 'iloc'):
        volume = int(volume_val.iloc[0]) if isinstance(volume_val, pd.Series) else int(volume_val)
    else:
        volume = int(volume_val)

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
    predicted_price, confidence, model_score = predict_stock_price(df, prediction_days)

    # Display metrics
    st.subheader(f"📊 {ticker} - {ALL_TICKERS.get(ticker, 'N/A')} Overview")

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
        if predicted_price is not None:
            pred_change = ((predicted_price - close_price) / close_price) * 100
            pred_class = "prediction-positive" if pred_change > 0 else "prediction-negative"
            st.markdown(f"""
            <div class="metric-card">
                <h4>ML Prediction ({prediction_days} days)</h4>
                <p class="{pred_class}">Predicted Price: ${predicted_price:.2f}</p>
                <p>Expected Change: <span class="{pred_class}">{pred_change:.2f}%</span></p>
                <p>Model Confidence: {confidence:.2%}</p>
                <p>Model Score: {model_score:.4f}</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="metric-card">
                <h4>ML Prediction</h4>
                <p>Insufficient data for reliable prediction</p>
            </div>
            """, unsafe_allow_html=True)

    with col6:
        # 52-week high/low
        if high_52 != low_52:  # Avoid division by zero
            width_percent = ((close_price - low_52) / (high_52 - low_52)) * 100
        else:
            width_percent = 50

        st.markdown(f"""
        <div class="metric-card">
            <h4>52-Week Range</h4>
            <p>High: ${high_52:.2f} | Low: ${low_52:.2f}</p>
            <div style="background: #e0e0e0; height: 10px; border-radius: 5px; margin: 10px 0;">
                <div style="background: #00C805; height: 100%; border-radius: 5px; width: {width_percent}%;"></div>
            </div>
            <p>Current: ${close_price:.2f}</p>
        </div>
        """, unsafe_allow_html=True)

    # Tabs: Price Charts, Technical Indicators, ML Insights
    tabs = st.tabs(["📈 Price Charts", "📊 Technical Indicators", "🤖 ML Insights"])

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

    # Tab 3: ML Insights
    with tabs[2]:
        if predicted_price is not None and confidence >= confidence_threshold:
            st.subheader("Machine Learning Predictions")

            # Generate predictions for multiple days
            future_dates = [datetime.now() + timedelta(days=i) for i in range(1, prediction_days + 1)]
            future_predictions = []

            # Simple projection based on the prediction
            current_price = close_price
            daily_change = (predicted_price / current_price) ** (1 / prediction_days) - 1

            for i in range(1, prediction_days + 1):
                future_price = current_price * (1 + daily_change) ** i
                future_predictions.append(future_price)

            # Create prediction chart
            fig_pred = go.Figure()

            # Historical data
            fig_pred.add_trace(go.Scatter(
                x=df['Date'][-30:],  # Last 30 days
                y=df['Close'][-30:],
                mode='lines',
                name='Historical',
                line=dict(color='#00C805', width=2)
            ))

            # Prediction data
            fig_pred.add_trace(go.Scatter(
                x=future_dates,
                y=future_predictions,
                mode='lines+markers',
                name='Prediction',
                line=dict(color='#FF9900', width=2, dash='dash')
            ))

            # Confidence interval
            upper_bound = [p * (1 + (1 - confidence) / 2) for p in future_predictions]
            lower_bound = [p * (1 - (1 - confidence) / 2) for p in future_predictions]

            fig_pred.add_trace(go.Scatter(
                x=future_dates + future_dates[::-1],
                y=upper_bound + lower_bound[::-1],
                fill='toself',
                fillcolor='rgba(255, 153, 0, 0.2)',
                line=dict(color='rgba(255,255,255,0)'),
                name='Confidence Interval'
            ))

            fig_pred.update_layout(
                title=f"{prediction_days}-Day Price Prediction",
                xaxis_title="Date",
                yaxis_title="Price ($)",
                template="plotly_white",
                height=500
            )
            st.plotly_chart(fig_pred, use_container_width=True)

            # Trading signals based on indicators
            st.subheader("Trading Signals")

            signals = []

            # RSI signal
            if 'RSI' in df.columns:
                rsi = df['RSI'].iloc[-1]
                if rsi > 70:
                    signals.append(("RSI", "Overbought", "Sell", "red"))
                elif rsi < 30:
                    signals.append(("RSI", "Oversold", "Buy", "green"))

            # MACD signal
            if all(col in df.columns for col in ['MACD', 'MACD_Signal']):
                macd = df['MACD'].iloc[-1]
                signal = df['MACD_Signal'].iloc[-1]
                if macd > signal:
                    signals.append(("MACD", "Bullish crossover", "Buy", "green"))
                else:
                    signals.append(("MACD", "Bearish crossover", "Sell", "red"))

            # Moving Average signal
            if all(col in df.columns for col in ['MA_10', 'MA_50']):
                ma10 = df['MA_10'].iloc[-1]
                ma50 = df['MA_50'].iloc[-1]
                if ma10 > ma50:
                    signals.append(("Moving Average", "Golden cross", "Buy", "green"))
                else:
                    signals.append(("Moving Average", "Death cross", "Sell", "red"))

            # Display signals
            if signals:
                for indicator, condition, action, color in signals:
                    st.markdown(f"""
                    <div style="background-color: #f8f9fa; padding: 10px; border-radius: 5px; margin: 5px 0; border-left: 4px solid {color}">
                        <strong>{indicator}</strong>: {condition} - <strong>{action}</strong>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No strong trading signals detected based on current indicators.")

        else:
            st.warning("Insufficient data or low confidence for ML predictions. Try selecting a longer time period.")

            # Show indicator summary instead
            st.subheader("Technical Indicator Summary")

            if 'RSI' in df.columns:
                rsi = df['RSI'].iloc[-1]
                st.write(
                    f"**RSI**: {rsi:.2f} {'(Overbought)' if rsi > 70 else '(Oversold)' if rsi < 30 else '(Neutral)'}")

            if all(col in df.columns for col in ['MACD', 'MACD_Signal']):
                macd = df['MACD'].iloc[-1]
                signal = df['MACD_Signal'].iloc[-1]
                st.write(f"**MACD**: {macd:.4f} | **Signal**: {signal:.4f} | **Difference**: {macd - signal:.4f}")

            if all(col in df.columns for col in ['MA_10', 'MA_50']):
                ma10 = df['MA_10'].iloc[-1]
                ma50 = df['MA_50'].iloc[-1]
                st.write(
                    f"**10-Day MA**: ${ma10:.2f} | **50-Day MA**: ${ma50:.2f} | **Spread**: {((ma10 - ma50) / ma50) * 100:.2f}%")

    # Display raw data
    with st.expander("View Raw Data"):
        st.dataframe(df.tail(20), use_container_width=True)


def analyze_stock(ticker: str, period: str, prediction_days: int, confidence_threshold: float):
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

        # Test database connection first
        db_connected = create_database()

        # Load to database using ETL load function
        if db_connected:
            try:
                success = load_to_postgres(df, table_name=ticker.lower())
                if success:
                    st.sidebar.success(f"{ticker} data saved to database")
                else:
                    st.sidebar.warning(f"Could not save {ticker} to database")
            except Exception as e:
                st.sidebar.warning(f"Database error: {e}")
        else:
            st.sidebar.warning("Database not connected. Data won't be saved.")

        # Display stock analysis
        display_stock_analysis(ticker, df, latest, prediction_days, confidence_threshold)

    except Exception as e:
        st.error(f"Error loading data for '{ticker}': {str(e)}")


def main():
    """Main application function"""
    st.markdown('<h1 class="main-header"> Advanced Stock Analysis Dashboard</h1>', unsafe_allow_html=True)

    # Sidebar
    st.sidebar.header("Settings")
    selected_period = st.sidebar.selectbox(
        "Select Time Period",
        list(PERIOD_OPTIONS.keys()),
        index=2
    )
    period_value = PERIOD_OPTIONS[selected_period]

    st.sidebar.header("ML Prediction Settings")
    prediction_days = st.sidebar.slider("Days to predict ahead", 1, 30, 7)
    ml_confidence_threshold = st.sidebar.slider("ML Confidence Threshold", 0.1, 0.9, 0.7)

    # Top Stocks
    st.subheader("Top 10 Stocks")
    display_top_stocks()

    # Stock Search
    st.subheader("Search Any Stock")
    search_input = st.text_input("Type ticker or company name", key="search").upper()

    suggestions = {}
    if search_input:
        suggestions = {k: v for k, v in ALL_TICKERS.items() if search_input in k or search_input in v.upper()}

    if suggestions:
        selected_ticker = st.selectbox(
            "Select stock",
            list(suggestions.keys()),
            format_func=lambda x: f"{x} - {suggestions[x]}"
        )
    else:
        selected_ticker = st.selectbox(
            "Select stock",
            list(ALL_TICKERS.keys()),
            format_func=lambda x: f"{x} - {ALL_TICKERS[x]}"
        )

    if selected_ticker:
        analyze_stock(selected_ticker, period_value, prediction_days, ml_confidence_threshold)
    else:
        st.info("Select a stock from the sidebar or search for a ticker to begin analysis.")

    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666;">
        <p>Advanced Stock Analysis Dashboard | Powered by yFinance, Streamlit, and Machine Learning</p>
        <p>Disclaimer: This is for educational purposes only. Not financial advice.</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()