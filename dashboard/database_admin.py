"""Password-protected manual price cleanup controls."""
import hashlib
import hmac
import os
import time
from datetime import date
import streamlit as st


def setting(name):
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        pass
    return os.getenv(name, '')


def authorized():
    secret = setting('DATABASE_ADMIN_TOKEN')
    saved = st.session_state.get('database_admin_auth', {})
    return bool(len(secret) >= 24 and
                time.monotonic() - saved.get('at', float('-inf')) < 900 and
                hmac.compare_digest(saved.get('fingerprint', ''),
                                    hashlib.sha256((secret + '\0' + setting('DATABASE_URL')).encode()).hexdigest()))


def render_cleanup(catalog):
    with st.expander('Delete saved database data'):
        secret = setting('DATABASE_ADMIN_TOKEN')
        database_url = setting('DATABASE_URL')
        if len(secret) < 24 or not database_url:
            st.info('Database cleanup is locked. The app owner must configure DATABASE_URL and a DATABASE_ADMIN_TOKEN of at least 24 characters in Streamlit secrets.')
            return
        if not authorized():
            st.caption('Administrator access expires after 15 minutes. Database cleanup does not affect live API prices or memory caches.')
            with st.form('database_admin_login', clear_on_submit=True):
                password = st.text_input('Database administrator password', type='password', max_chars=256)
                login = st.form_submit_button('Unlock database cleanup')
            if login:
                last = st.session_state.get('database_admin_attempt', float('-inf'))
                now = time.monotonic()
                if now - last < 5:
                    st.warning('Wait five seconds before another sign-in attempt.')
                else:
                    st.session_state.database_admin_attempt = now
                    if hmac.compare_digest(password.encode(), secret.encode()):
                        st.session_state.database_admin_auth = {
                            'at': now, 'fingerprint': hashlib.sha256((secret + '\0' + database_url).encode()).hexdigest()}
                        st.session_state.pop('database_price_tables', None)
                        st.rerun()
                    else:
                        st.warning('Administrator password did not match.')
            return
        st.caption('Choose old rows by date, or all rows including newly saved data. Tables are kept. This action is permanent through the app; download a backup first if needed.')
        if st.button('Lock database cleanup'):
            st.session_state.pop('database_admin_auth', None)
            st.session_state.pop('database_price_tables', None)
            st.rerun()
        legacy = set(symbol.lower() for symbol in catalog)
        legacy.update(name.strip() for name in setting('DATABASE_LEGACY_STOCK_TABLES').split(',') if name.strip())
        if st.button('Refresh saved price tables'):
            from etl.cleanup import list_price_tables
            try:
                st.session_state.database_price_tables = list_price_tables(database_url, legacy)
            except Exception:
                st.session_state.pop('database_price_tables', None)
                st.error('Could not list saved price tables. Check the database connection and permissions.')
        tables = st.session_state.get('database_price_tables')
        if tables is None:
            st.info('Click Refresh saved price tables to inspect the database. This button queries the table list. Shared price storage operates separately.')
            return
        if not tables:
            st.info('No eligible stock-price tables were found. Unknown legacy table names can be added by the owner through DATABASE_LEGACY_STOCK_TABLES.')
            return
        with st.form('delete_database_rows'):
            selected = st.multiselect('Saved price tables', [row['table'] for row in tables])
            mode = st.radio('Rows to delete', ['Rows before a date', 'All rows (old and new)'])
            cutoff = st.date_input('Delete rows dated before', value=date.today(), help='The selected date itself is kept. Ignored when deleting all rows.')
            phrase = st.text_input('Type DELETE to confirm', max_chars=6)
            confirmed = st.checkbox('I understand this permanently deletes the selected saved rows.')
            delete = st.form_submit_button('Delete selected saved rows')
        if delete:
            if not authorized():
                st.error('Administrator access expired. Sign in again.')
            elif not selected or phrase != 'DELETE' or not confirmed:
                st.warning('Select tables, type DELETE, and check the confirmation box before deleting.')
            else:
                from etl.cleanup import delete_price_rows
                try:
                    counts = delete_price_rows(database_url, legacy, selected,
                                               before=cutoff if mode == 'Rows before a date' else None)
                    st.success('Deleted saved rows: ' + ', '.join(f'{name}: {count:,}' for name, count in counts.items()))
                    st.session_state.pop('database_price_tables', None)
                except Exception:
                    st.error('Cleanup failed and the transaction was rolled back. Check the connection, table dependencies, and database permissions.')
