"""Explicit page registration supports updates without a process restart."""
import sys
from pathlib import Path
import streamlit as st

st.set_page_config(page_title='Stock Explorer', page_icon='📈', layout='wide')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.runtime import prepare_runtime
prepare_runtime()

page = st.navigation([
    st.Page('home.py', title='Stock Explorer', icon='📈', default=True),
    st.Page('pages/admin.py', title='Database admin', icon='🔒', url_path='admin'),
], position='hidden')
page.run()
