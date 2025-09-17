from sqlalchemy import create_engine, text
import pandas as pd
import os
import streamlit as st


def get_database_url():
    """Get database URL from environment variables or Streamlit secrets"""
    # First try Streamlit secrets (for cloud deployment)
    try:
        if hasattr(st, 'secrets') and 'DATABASE_URL' in st.secrets:
            return st.secrets['DATABASE_URL']
    except:
        pass

    # Then try environment variable
    DB_URL = os.environ.get('DATABASE_URL')
    if DB_URL:
        return DB_URL

    # Fallback to local database if no environment variable
    DB_NAME = "stocks"
    DB_USER = "bhuwanbokati"
    DB_HOST = "localhost"
    DB_PORT = 5432
    return f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def create_database():
    """Check database connection"""
    try:
        DB_URL = get_database_url()

        # Ensure proper URL format for SQLAlchemy
        if DB_URL.startswith('postgres://'):
            db_url = DB_URL.replace('postgres://', 'postgresql://', 1)
        else:
            db_url = DB_URL

        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()
            st.sidebar.success(f"Connected to PostgreSQL")
        return True
    except Exception as e:
        st.sidebar.warning(f"Database connection failed: {e}")
        return False


def load_to_postgres(df: pd.DataFrame, table_name='stocks'):
    """Load dataframe to PostgreSQL"""
    try:
        DB_URL = get_database_url()

        # Ensure proper URL format for SQLAlchemy
        if DB_URL.startswith('postgres://'):
            db_url = DB_URL.replace('postgres://', 'postgresql://', 1)
        else:
            db_url = DB_URL

        engine = create_engine(db_url)
        df.to_sql(table_name, engine, if_exists='replace', index=False)
        st.sidebar.success(f"Table '{table_name}' loaded successfully")
        return True
    except Exception as e:
        st.sidebar.warning(f"Error loading to database: {e}")
        return False


def fetch_from_postgres(table_name='stocks'):
    """Fetch data from PostgreSQL"""
    try:
        DB_URL = get_database_url()

        if DB_URL.startswith('postgres://'):
            db_url = DB_URL.replace('postgres://', 'postgresql://', 1)
        else:
            db_url = DB_URL

        engine = create_engine(db_url)
        df = pd.read_sql_table(table_name, engine)
        return df
    except Exception as e:
        st.sidebar.warning(f"Error fetching data: {e}")
        return None