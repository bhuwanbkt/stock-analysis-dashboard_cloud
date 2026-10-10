import os
import sys
import time
from pathlib import Path

import streamlit as st
st.set_page_config(page_title='Stock Explorer', page_icon='📈', layout='wide')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.graph_objects as go
from dashboard.catalog import load_catalog
from dashboard.market import get_history, get_profile, get_forecast, get_company_matches, normalize_symbol, MarketUnavailable, ForecastBusy
from dashboard.analysis import PERIOD_MONTHS, select_period, summarize, compare_returns
from etl.transform import add_indicators
from dashboard.database_admin import render_cleanup, authorized

CATALOG = load_catalog()
st.markdown('''<style>
.block-container {max-width:1200px; padding-top:2rem;}
[data-testid="stMetric"] {border:1px solid #8883; border-radius:12px; padding:14px;}
h1 {letter-spacing:-1px;}
</style>''', unsafe_allow_html=True)


def cooldown(action, seconds=20):
    now = time.monotonic()
    previous = st.session_state.get('last_' + action, float('-inf'))
    if now - previous < seconds:
        st.info(f'Please wait {seconds} seconds between {action.replace("_", " ")} requests.')
        return False
    st.session_state['last_' + action] = now
    return True


def select_company(candidate, record):
    custom = dict(list(st.session_state.get('custom_companies', {}).items())[-9:])
    if candidate not in CATALOG:
        custom[candidate] = record
        st.session_state.custom_companies = custom
    st.session_state.active_symbol = candidate
    st.session_state.pop('company_picker', None)
    st.rerun()


def price_chart(frame, kind='Line', averages=False):
    fig = go.Figure()
    if kind == 'Candlestick':
        fig.add_trace(go.Candlestick(x=frame.Date, open=frame.Open, high=frame.High,
                                    low=frame.Low, close=frame.Close, name='Adjusted price'))
    else:
        fig.add_trace(go.Scatter(x=frame.Date, y=frame.Close, name='Adjusted close',
                                line=dict(color='#2563eb', width=2)))
    if averages:
        for window, color in [(10, '#f59e0b'), (50, '#8b5cf6')]:
            fig.add_trace(go.Scatter(x=frame.Date, y=frame[f'MA_{window}'], name=f'{window}-session average',
                                    line=dict(color=color, width=1.3, dash='dot')))
    fig.update_layout(height=390, margin=dict(l=0,r=0,t=12,b=0), hovermode='x unified',
                      xaxis_rangeslider_visible=False, yaxis_title='Adjusted price',
                      legend=dict(orientation='h', y=1.08))
    st.plotly_chart(fig, use_container_width=True)


def main():
    st.title('Stock Explorer')
    st.caption('Understand price history, compare companies, and inspect experimental forecasts.')
    render_cleanup(CATALOG)
    custom = st.session_state.get('custom_companies', {})
    companies = {**CATALOG, **custom}
    if 'active_symbol' not in st.session_state:
        st.session_state.active_symbol = 'AAPL'
    symbols = list(companies)
    preferred = st.session_state.active_symbol
    symbol = st.selectbox('Search a company', symbols, index=symbols.index(preferred) if preferred in symbols else 0,
                          format_func=lambda value: f"{companies[value]['name']} ({value})", key='company_picker')
    st.session_state.active_symbol = symbol
    st.caption('Type a name or ticker inside the dropdown. The saved catalog needs no API request.')
    with st.expander('Company or ticker not listed?'):
        with st.form('company_lookup'):
            query = st.text_input('Search provider by company name', max_chars=60, placeholder='Sony')
            searched = st.form_submit_button('Find companies')
        if searched and cooldown('company_search'):
            st.session_state.pop('company_matches', None)
            try:
                with st.spinner('Finding company listings...'):
                    matches = get_company_matches(' '.join(query.split()).casefold())
                st.session_state.company_matches = matches
                if not matches:
                    st.info('No stock listings were returned. Try a different name or a known ticker below.')
            except (ValueError, MarketUnavailable) as exc:
                st.info(str(exc))
        matches = st.session_state.get('company_matches', [])
        if matches:
            by_symbol = {row['symbol']: row for row in matches}
            selected = st.selectbox('Choose a company listing', list(by_symbol),
                                    format_func=lambda value: f"{by_symbol[value]['name']} ({value}) · {by_symbol[value]['exchange']}")
            st.caption('A company may trade on several exchanges. Choose the listing you want; daily history is checked before opening it.')
            if st.button('Open selected company') and cooldown('ticker_lookup'):
                try:
                    with st.spinner('Checking daily price history...'):
                        get_history(selected)
                    select_company(selected, by_symbol[selected])
                except MarketUnavailable as exc:
                    st.warning(str(exc))
        st.caption('Already know the ticker? Look it up directly below.')
        with st.form('ticker_lookup'):
            raw = st.text_input('Enter an additional ticker', max_chars=15, placeholder='COST or BRK-B')
            submitted = st.form_submit_button('Look up ticker')
        if submitted and cooldown('ticker_lookup'):
            try:
                candidate = normalize_symbol(raw)
                with st.spinner('Checking daily price history...'):
                    get_history(candidate)
                select_company(candidate, companies.get(candidate) or {
                    'symbol': candidate, 'name': candidate, 'overview': None,
                    'currency': None, 'source': 'Validated daily price history', 'updated_at': None})
            except (ValueError, MarketUnavailable) as exc:
                st.warning(str(exc))

    period = st.sidebar.selectbox('Chart period', list(PERIOD_MONTHS), index=3)
    st.sidebar.caption('Daily bars · Shared four-hour price cache · No database writes during browsing')
    st.sidebar.caption('Free Streamlit apps may sleep after 12 hours without traffic. On the sleeping page, click “Yes, get this app back up!”')
    profile = st.session_state.get('profiles', {}).get(symbol, companies[symbol])
    currency = profile.get('currency')
    price_label = f'Adjusted close ({currency})' if currency else 'Adjusted close (quote units)'
    st.subheader(f"{profile['name']} · {symbol}")
    try:
        with st.spinner('Loading daily prices...'):
            packet = get_history(symbol, '5y' if period == '5 Years' else '2y')
    except MarketUnavailable as exc:
        st.warning(str(exc))
        st.caption('A provider outage or rate limit does not necessarily mean the ticker is invalid.')
        return
    history = add_indicators(packet['prices'].copy())
    frame = select_period(history, period)
    if len(frame) < 2:
        st.info('Not enough price history for this period.')
        return
    latest, previous = history.iloc[-1], history.iloc[-2]
    stats = summarize(frame)
    day_change = (latest.Close / previous.Close - 1) * 100
    c1,c2,c3,c4 = st.columns(4)
    c1.metric(price_label, f'{latest.Close:,.2f}', f'{day_change:+.2f}% vs previous bar')
    c2.metric(f'{period} return', f"{stats['return_pct']:+.2f}%")
    c3.metric('Daily volatility', f"{stats['daily_volatility_pct']:.2f}%" if stats['daily_volatility_pct'] is not None else '—')
    c4.metric('Largest period drawdown', f"{stats['max_drawdown_pct']:.2f}%")
    st.caption(f"Latest bar: {latest.Date:%Y-%m-%d} · Downloaded: {packet['fetched_at'][:16].replace('T',' ')} UTC · Yahoo Finance via yfinance")
    downloaded = packet.get('downloaded_rows', len(history))
    st.caption(f"History: {history.Date.iloc[0]:%Y-%m-%d} to {latest.Date:%Y-%m-%d} · {downloaded:,} downloaded rows · {len(history):,} valid daily rows · {len(frame):,} rows in this chart. Browsing saves no rows to Postgres.")
    st.caption('Daily prices are adjusted for corporate actions, may be delayed, and can include an unfinished session. Returns are price returns, not a trading-strategy result.')

    # Render only the selected view. Streamlit tabs eagerly execute every tab body.
    view = st.radio('View', ['Overview', 'Indicators', 'Compare', 'Forecast quality'], horizontal=True, label_visibility='collapsed')
    if view == 'Overview':
        col1,col2 = st.columns([1,2])
        kind = col1.radio('Chart style', ['Line','Candlestick'], horizontal=True)
        averages = col2.checkbox('Show moving averages', value=True)
        price_chart(frame, kind, averages)
        st.subheader('What the data says')
        movement = 'rose' if stats['return_pct'] >= 0 else 'fell'
        st.write(f"During this period, {symbol} {movement} {abs(stats['return_pct']):.2f}%. Its largest drop from a previous period high was {abs(stats['max_drawdown_pct']):.2f}%.")
        ma50 = history.MA_50.iloc[-1]
        if pd.notna(ma50):
            distance = (latest.Close / ma50 - 1) * 100
            st.write(f"The latest close is {abs(distance):.2f}% {'above' if distance >= 0 else 'below'} the 50-session average. This describes past prices; it is not a buy or sell instruction.")
        with st.expander('Company overview'):
            st.write(profile.get('overview') or 'No saved overview yet. Prices and analysis work independently of the profile API.')
            if profile.get('sector'):
                st.caption(f"{profile['sector']} · {profile.get('industry') or 'Industry unavailable'}")
            st.caption(f"Source: {profile['source']} · Updated: {profile.get('updated_at') or 'Pending'}")
            if st.button('Load company overview') and cooldown('profile_lookup',60):
                try:
                    fetched = get_profile(symbol)
                    profiles = dict(list(st.session_state.get('profiles', {}).items())[-9:])
                    profiles[symbol] = fetched
                    st.session_state.profiles = profiles
                    st.rerun()
                except MarketUnavailable as exc:
                    st.info(str(exc))
        with st.expander('Daily prices and export'):
            st.caption('Prices stay in a shared memory cache for up to four hours, not in Postgres. A restart clears the cache. Any older database exports remain until explicitly replaced or removed; there is no automatic deletion job.')
            st.dataframe(frame[['Date','Open','High','Low','Close','Volume']].tail(30), hide_index=True)
            st.download_button('Download selected daily prices (CSV)',
                               frame[['Date','Open','High','Low','Close','Volume']].to_csv(index=False),
                               file_name=f'{symbol}_daily_prices.csv', mime='text/csv')
            if os.getenv('ENABLE_DATABASE_EXPORT') == '1' and authorized() and st.button('Save prices to database'):
                from etl.load import load_to_postgres
                import hashlib
                table_name = 'prices_' + hashlib.sha256(symbol.encode()).hexdigest()[:12]
                if load_to_postgres(frame, table_name=table_name):
                    st.success('Export saved. It persists until explicitly removed or replaced.')
                else:
                    st.warning('Database export failed.')
    elif view == 'Indicators':
        indicator = st.selectbox('Indicator', ['Volume','RSI','MACD'])
        fig=go.Figure()
        if indicator == 'Volume':
            fig.add_trace(go.Bar(x=frame.Date,y=frame.Volume,name='Volume'))
        elif indicator == 'RSI':
            fig.add_trace(go.Scatter(x=frame.Date,y=frame.RSI,name='RSI'))
            fig.add_hline(y=70,line_dash='dot');fig.add_hline(y=30,line_dash='dot')
            st.caption('RSI summarizes recent gains and losses. Readings above 70 or below 30 do not guarantee a reversal.')
        else:
            fig.add_trace(go.Scatter(x=frame.Date,y=frame.MACD,name='MACD'))
            fig.add_trace(go.Scatter(x=frame.Date,y=frame.MACD_Signal,name='Signal'))
            st.caption('MACD compares two moving averages. It describes momentum rather than predicting a guaranteed outcome.')
        fig.update_layout(height=380,margin=dict(l=0,r=0,t=10,b=0),hovermode='x unified')
        st.plotly_chart(fig,use_container_width=True)
    elif view == 'Compare':
        other=st.selectbox('Compare with', [s for s in companies if s != symbol],
                           format_func=lambda value:f"{companies[value]['name']} ({value})")
        if st.button('Compare stocks') and cooldown('comparison',20):
            try:
                other_packet=get_history(other,'5y' if period == '5 Years' else '2y')
                aligned=compare_returns(frame, select_period(other_packet['prices'],period),symbol,other)
                st.session_state.comparison={'key':(symbol,other,period,packet['fetched_at']),'data':aligned}
            except (ValueError,MarketUnavailable) as exc:
                st.info(str(exc))
        saved=st.session_state.get('comparison')
        if saved and saved['key']==(symbol,other,period,packet['fetched_at']):
            aligned=saved['data'];fig=go.Figure()
            for label in [symbol,other]:
                fig.add_trace(go.Scatter(x=aligned.Date,y=aligned[label],name=label))
            fig.update_layout(height=390,yaxis_title='Price return (%)',hovermode='x unified',margin=dict(l=0,r=0,t=10,b=0))
            st.plotly_chart(fig,use_container_width=True)
            st.caption(f"Both start at 0% on the first shared date: {aligned.Date.iloc[0]:%Y-%m-%d}. Latest shared date: {aligned.Date.iloc[-1]:%Y-%m-%d}.")
        else:
            st.info('Choose another company and click Compare stocks. No comparison API call runs before the button is clicked.')
    else:
        st.subheader('Experimental forecast')
        horizon=st.selectbox('Trading sessions ahead',[1,5,7,10,20,30],index=2)
        st.caption('Ridge regression, Random Forest, and gradient boosting compete with unchanged price in the same earlier chronological validation windows. The best validation method is tested on a separate latest window.')
        if st.button('Run forecast') and cooldown('forecast',20):
            try:
                with st.spinner('Checking historical forecast quality...'):
                    result=get_forecast(symbol,packet['prices'],horizon)
                st.session_state.forecast_result={'key':(symbol,horizon,str(latest.Date),packet['fetched_at']),'result':result}
            except (ValueError,MarketUnavailable,ForecastBusy) as exc:
                st.info(str(exc))
        saved=st.session_state.get('forecast_result')
        if saved and saved['key']==(symbol,horizon,str(latest.Date),packet['fetched_at']):
            result=saved['result']
            if result['available']:
                st.metric('Estimated endpoint (quote units)',f"{result['predicted_price']:,.2f}",f"{result['predicted_return']:+.2%}")
                st.write(f"Selected method: **{result['model']}**")
                if result.get('validation_scores'):
                    scores = pd.DataFrame(result['validation_scores']).rename(columns={
                        'method': 'Method', 'mae_pct': 'Validation error (percentage points)', 'selected': 'Selected'})
                    st.dataframe(scores, hide_index=True)
                    st.caption('Lower validation error is better. This table uses earlier development data; it is not the separate test result or a confidence score.')
                a,b=st.columns(2)
                a.metric('Selected method: average return error',f"{result['mae_pct']:.2f} percentage points")
                b.metric('Unchanged-price baseline error',f"{result['baseline_mae_pct']:.2f} percentage points")
                if result['model']=='Unchanged-price baseline':
                    st.info('None of the learned methods beat unchanged price during development validation. An unchanged estimate is a fallback, not evidence the stock will stay flat.')
                elif not result['beats_baseline_on_holdout']:
                    st.warning('The selected model did not beat unchanged price on the separate latest test window.')
                else:
                    st.success('The selected model had lower average error on this latest test window. Future performance is unknown.')
                st.caption(f"{result['test_rows']} test origins · {result['training_rows']} labelled rows · Based on bar {result['as_of'][:10]}")
                if 'input_rows' in result:
                    st.caption(f"Model input: {result['input_rows']} daily rows from {result['history_start'][:10]}. Features use past prices and volume; labels require a known price {horizon} trading sessions later. Only the selected method is refit for the endpoint estimate.")
            else:
                st.info(result['reason'])
        st.caption('Trading sessions exclude weekends and exchange holidays. Overlapping targets are correlated. Historical error is not a confidence probability. No daily path or guaranteed future return is implied.')
    st.divider()
    st.caption('Educational analysis · No investment recommendations · No LLM calls · No required database · Memory caches reset when the app restarts.')


if __name__=='__main__':
    main()
