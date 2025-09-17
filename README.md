# Stock ETL Dashboard

A comprehensive stock analysis dashboard that extracts, transforms, and loads stock data with technical indicators, machine learning predictions, and interactive visualizations.

## Features

- **Real-time Stock Data**: Fetches live stock data using Yahoo Finance API
- **Technical Indicators**: Calculates RSI, MACD, Moving Averages, Bollinger Bands, and more
- **Machine Learning Predictions**: Uses Random Forest to predict future stock prices
- **Interactive Dashboard**: Built with Streamlit for real-time visualization
- **PostgreSQL Integration**: Stores processed data in a relational database
- **Comprehensive Analysis**: Includes candlestick charts, volume analysis, and trading signals

## Project Structure
```
stock_etl_dashboard/
├── .venv/ # Python virtual environment
├── .idea/ # PyCharm IDE configuration
├── dashboard/
│   └── app.py # Streamlit dashboard application
├── etl/
│   ├── __init__.py # Package initialization
│   ├── extract.py # Data extraction from Yahoo Finance
│   ├── transform.py # Technical indicator calculations
│   └── load.py # Database loading functionality
├── tests/ # Test files
├── .gitignore # Git ignore rules
├── requirements.txt # Python dependencies
├── Dockerfile # Containerization configuration
├── docker-compose.yml # Multi-container setup
└── README.md # Project documentation
```

## Installation

### Prerequisites

- Python 3.8+
- PostgreSQL
- pip

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd stock-analysis-dashboard_cloud
```

2. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On macOS/Linux
.venv\Scripts\activate   # On Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up PostgreSQL database:
```bash
# Ensure PostgreSQL is running
brew services start postgresql  # On macOS with Homebrew
sudo service postgresql start   # On Linux
```

5. Configure database credentials in `etl/load.py` if needed:
```python
DB_NAME = "stocks"
DB_USER = "bhuwanbokati"  # Change to your PostgreSQL username
DB_HOST = "localhost"
DB_PORT = 5432
```

## Usage

### Running the Dashboard
```bash
streamlit run dashboard/app.py
```
The dashboard will open in your browser at http://localhost:8501.

### ETL Process
The application follows an ETL (Extract, Transform, Load) pattern:

- **Extract**: Fetches stock data from Yahoo Finance API  
- **Transform**: Calculates technical indicators and prepares data for analysis  
- **Load**: Stores processed data in PostgreSQL database  

## Available Technical Indicators
- Moving Averages (10, 20, 50, 200 days)
- Exponential Moving Averages (12, 26 days)
- MACD (Moving Average Convergence Divergence)
- RSI (Relative Strength Index)
- Bollinger Bands
- Stochastic Oscillator
- Average True Range (ATR)
- On-Balance Volume (OBV)
- Price Rate of Change (ROC)
- Volatility measurements

## Machine Learning Features
The application includes a Random Forest Regressor for stock price prediction:

- Predicts prices for 1-30 days ahead
- Provides confidence scores for predictions
- Generates trading signals based on technical indicators
- Includes confidence intervals for predictions

## Database Schema
The application stores data in PostgreSQL with the following structure:

- **Table name**: Matches the stock ticker (e.g., `aapl` for Apple)  
- **Columns**: Date, Open, High, Low, Close, Volume, plus all technical indicators  
- Automatic database creation if not exists  

## Configuration

### Time Period Options
The dashboard supports multiple time periods:

- 1 Month
- 3 Months
- 6 Months
- 1 Year
- 2 Years
- 5 Years

### Supported Stocks
The application includes predefined lists of popular stocks:

- Top 10 stocks (AAPL, MSFT, GOOGL, AMZN, TSLA, META, NVDA, NFLX, INTC, AMD)  
- Additional stocks (PLTR, UBER, JPM, V, DIS, PYPL, GS, BA, XOM, JNJ)  
- Custom stock search functionality  

## Code Overview

### ETL Modules
**extract.py**  
Handles data extraction from Yahoo Finance API with proper error handling.

**transform.py**  
Calculates comprehensive technical indicators including RSI, MACD, Moving Averages, Bollinger Bands, and more.

**load.py**  
Manages PostgreSQL database operations including automatic database creation and data loading.

### Dashboard Application
The main dashboard application (`app.py`) built with Streamlit provides:

- Interactive stock selection and search
- Real-time price charts with technical indicators
- Machine learning predictions
- Trading signals based on technical analysis
- Database integration for data persistence

## Docker Support
The project includes Docker configuration for containerized deployment:

```bash
# Build and run with Docker Compose
docker-compose up --build

# Or build individually
docker build -t stock-dashboard .
```

## Dependencies
Key Python dependencies include:

- streamlit
- yfinance
- plotly
- pandas
- numpy
- scikit-learn
- sqlalchemy
- psycopg2-binary

See `requirements.txt` for complete list.

## Troubleshooting

### Common Issues

**Database Connection Errors:**
- Ensure PostgreSQL is running
- Verify database credentials in `etl/load.py`

**Missing Dependencies:**
- Run `pip install -r requirements.txt`

**Yahoo Finance API Issues:**
- Check internet connection
- Verify ticker symbols are valid

**ML Prediction Failures:**
- Select a longer time period for more historical data

## Contributing
1. Fork the repository  
2. Create a feature branch  
3. Make your changes  
4. Add tests if applicable  
5. Submit a pull request  

## License
This project is licensed under the MIT License.

## Acknowledgments
- Yahoo Finance for providing stock data API  
- Streamlit for the interactive dashboard framework  
- PostgreSQL for database management  
- Scikit-learn for machine learning capabilities  
- Plotly for interactive visualizations