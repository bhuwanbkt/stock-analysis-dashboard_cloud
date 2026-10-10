"""Separate administrator page. Market-data requests do not run here."""
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.catalog import load_catalog
from dashboard.database_admin import render_cleanup

st.title('Database administration')
st.caption('Manage saved price data using your private administrator password.')
if st.button('Back to Stock Explorer', icon='📈'):
    st.switch_page('home.py')
st.subheader('Delete saved database data')
render_cleanup(load_catalog(), standalone=True)
