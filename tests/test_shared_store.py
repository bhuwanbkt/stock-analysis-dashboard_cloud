from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
from sqlalchemy import create_engine, select, func, insert, update, text
from etl.shared_store import SharedStore, companies, prices, refresh, forecasts, maintenance
from dashboard.market import get_history

NOW=datetime(2026,10,10,tzinfo=timezone.utc)


def frame(start='2026-10-01', count=4, factor=1):
    values=pd.Series([100+i for i in range(count)],dtype=float)*factor
    return pd.DataFrame({'Date':pd.bdate_range(start,periods=count),'Open':values,'High':values+1,
                         'Low':values-1,'Close':values,'Volume':1000})


@pytest.fixture
def repo():
    engine=create_engine('sqlite://')
    store=SharedStore(engine);store.initialize()
    yield store
    engine.dispose()


def save(repo,symbol='AAPL',data=None,now=NOW):
    state,token=repo.claim_refresh(symbol,now)
    assert state=='claimed'
    data=frame() if data is None else data
    assert repo.finish_refresh(symbol,data,len(data),token,now)


def count(repo,table):
    with repo.transaction() as conn:return conn.scalar(select(func.count()).select_from(table))


def test_upsert_same_dates_and_full_adjustment_refresh(repo):
    save(repo)
    assert count(repo,prices)==4
    assert repo.claim_refresh('AAPL',NOW)[0]=='fresh'
    save(repo,data=frame(factor=.5),now=NOW+timedelta(days=1))
    result=repo.read_history('AAPL',NOW+timedelta(days=1))
    assert count(repo,prices)==4 and result['prices'].Close.iloc[0]==50
    assert result['persisted'] and not result['stale']
    assert repo.read_history('AAPL',NOW+timedelta(days=2))['stale']


def test_lease_fencing_busy_backoff_and_no_invalid_company(repo):
    status,old=repo.claim_refresh('UNKNOWN',NOW)
    assert status=='claimed' and count(repo,companies)==0
    assert repo.claim_refresh('UNKNOWN',NOW+timedelta(minutes=1))[0]=='busy'
    _,new=repo.claim_refresh('UNKNOWN',NOW+timedelta(minutes=4))
    assert new!=old
    assert not repo.finish_refresh('UNKNOWN',frame(),4,old,NOW+timedelta(minutes=4))
    repo.fail_refresh('UNKNOWN',old,NOW+timedelta(minutes=4))
    assert repo.claim_refresh('UNKNOWN',NOW+timedelta(minutes=4))[0]=='busy'
    repo.fail_refresh('UNKNOWN',new,NOW+timedelta(minutes=4))
    assert repo.claim_refresh('UNKNOWN',NOW+timedelta(minutes=5))[0]=='backoff'
    assert count(repo,companies)==0 and count(repo,prices)==0
    assert repo.claim_refresh('UNKNOWN',NOW+timedelta(minutes=10))[0]=='claimed'


def test_capacity_counts_pending_reservations_and_profile_slots(repo):
    with patch('etl.shared_store.MAX_COMPANIES',2):
        assert repo.claim_refresh('AAPL',NOW)[0]=='claimed'
        assert repo.claim_refresh('MSFT',NOW)[0]=='claimed'
        assert repo.claim_refresh('NVDA',NOW)[0]=='capacity'
        assert not repo.save_profile('NVDA',{'name':'Nvidia'},NOW)
        # A failed lookup releases its reservation without saving a company.
        with repo.transaction() as conn:
            token=conn.scalar(select(refresh.c.lease_token).where(refresh.c.symbol=='MSFT'))
        repo.fail_refresh('MSFT',token,NOW)
        assert repo.claim_refresh('NVDA',NOW)[0]=='claimed'


def test_outdated_history_does_not_save_empty_company(repo):
    _,token=repo.claim_refresh('OLD',NOW)
    assert not repo.finish_refresh('OLD',frame('2020-01-01'),4,token,NOW)
    assert count(repo,companies)==0


def test_profiles_keep_previous_overview_and_expire_after_30_days(repo):
    save(repo)
    assert repo.save_profile('AAPL',{'name':'Apple','overview':'Saved overview','currency':'USD'},NOW)
    repo.save_profile('AAPL',{'name':'Apple Inc.','overview':None},NOW+timedelta(days=3))
    profile=repo.read_profile('AAPL',NOW+timedelta(days=29))
    assert profile['overview']=='Saved overview' and profile['currency']=='USD'
    assert not profile['profile_stale']
    assert repo.read_profile('AAPL',NOW+timedelta(days=30))['profile_stale']


def forecast_result():
    return {'available':True,'as_of':'2026-10-01','horizon':2,'model':'Ridge regression',
            'predicted_return':.03,'predicted_price':103.}


def test_forecast_dedup_cap_and_observed_return_uses_same_adjustment_basis(repo):
    save(repo)
    result=forecast_result()
    assert repo.record_forecast('AAPL',result,'v1',NOW)
    assert repo.record_forecast('AAPL',{**result,'predicted_return':.99},'v1',NOW)
    assert count(repo,forecasts)==1
    with patch('etl.shared_store.MAX_FORECASTS',1):
        assert not repo.record_forecast('AAPL',result,'v2',NOW)
    save(repo,data=frame(factor=.5),now=NOW+timedelta(days=1))
    row=repo.forecast_history('AAPL')[0]
    assert row['Predicted return (%)']==3
    assert row['Observed return (%)']==pytest.approx(2)
    assert row['Status']=='Evaluated'


def test_forecasts_wait_for_horizon(repo):
    save(repo)
    result={**forecast_result(),'as_of':'2026-10-06','horizon':7}
    repo.record_forecast('AAPL',result,'v1',NOW)
    save(repo,now=NOW+timedelta(days=1))
    assert repo.forecast_history('AAPL')[0]['Status']=='Pending'


def test_weekly_cleanup_bounds_and_keeps_legacy_tables(repo):
    save(repo)
    with repo.transaction() as conn:
        conn.execute(text('CREATE TABLE aapl (id INTEGER)'))
        conn.execute(text('INSERT INTO aapl VALUES (1)'))
        conn.execute(insert(prices).values(symbol='AAPL',Date=pd.Timestamp('2024-10-09').date(),
            Open=1,High=1,Low=1,Close=1,Volume=1))
        conn.execute(insert(forecasts).values(symbol='AAPL',as_of=pd.Timestamp('2026-01-01').date(),horizon=1,
            model_version='v0',created_at=NOW-timedelta(days=91),result='{}'))
    assert repo.maintain(NOW)
    assert count(repo,prices)==4 and count(repo,forecasts)==0
    assert not repo.maintain(NOW+timedelta(days=6))
    assert repo.maintain(NOW+timedelta(days=7))
    with repo.transaction() as conn: assert conn.scalar(text('SELECT count(*) FROM aapl'))==1


def test_cleanup_failure_rolls_back_and_does_not_advance_timestamp(repo):
    original=repo.transaction
    from contextlib import contextmanager
    @contextmanager
    def broken():
        with original() as conn:
            yield conn
            raise RuntimeError('simulated failure before commit')
    with patch.object(repo,'transaction',broken):
        with pytest.raises(RuntimeError):repo.maintain(NOW)
    with repo.transaction() as conn:
        assert conn.scalar(select(maintenance.c.last_run).where(maintenance.c.key=='weekly_cleanup')) is None
    assert repo.maintain(NOW)


def packet(stale=False):
    return {'prices':frame(),'fetched_at':NOW.isoformat(),'downloaded_rows':4,
            'period':'2y','source':'Postgres','persisted':True,'stale':stale}


def test_fresh_database_prices_skip_provider_and_survive_memory_reset():
    db=MagicMock();db.read_history.return_value=packet()
    with patch('dashboard.market.get_store',return_value=db),patch('dashboard.market.yf.Ticker') as api:
        for _ in range(2):
            get_history.clear()
            assert get_history('AAPL')['source']=='Postgres'
        api.assert_not_called();db.claim_refresh.assert_not_called()
    get_history.clear()


@pytest.mark.parametrize('state',['claimed','busy','backoff'])
def test_stale_database_fallback_and_refresh_coordination(state):
    db=MagicMock();db.read_history.return_value=packet(True);db.claim_refresh.return_value=(state,'token')
    get_history.clear()
    with patch('dashboard.market.get_store',return_value=db),patch('dashboard.market.yf.Ticker') as api:
        api.return_value.history.side_effect=RuntimeError('private provider payload')
        result=get_history('AAPL')
        assert result['stale'] and result['persisted'] and result['source']=='Postgres'
        assert 'private' not in result['notice']
        assert api.call_count==(1 if state=='claimed' else 0)
    get_history.clear()


def test_five_year_download_never_saves_extra_history():
    get_history.clear()
    with patch('dashboard.market.get_store') as db,patch('dashboard.market.yf.Ticker') as api:
        api.return_value.history.return_value=frame().set_index('Date')
        result=get_history('AAPL','5y')
        assert not result['persisted'] and result['period']=='5y'
        db.assert_not_called()
    get_history.clear()


def test_write_failure_keeps_valid_prices_visible():
    db=MagicMock();db.read_history.return_value=None;db.claim_refresh.return_value=('claimed','token')
    db.finish_refresh.side_effect=RuntimeError('secret URL')
    get_history.clear()
    with patch('dashboard.market.get_store',return_value=db),patch('dashboard.market.yf.Ticker') as api:
        api.return_value.history.return_value=frame().set_index('Date')
        result=get_history('AAPL')
        assert len(result['prices'])==4 and not result['persisted']
        assert 'secret' not in result['notice']
    get_history.clear()


def test_price_rows_have_hard_bound_even_with_every_calendar_day(repo):
    data=frame('2024-11-01',700)
    data['Date']=pd.date_range('2024-11-01',periods=700)
    save(repo,data=data)
    assert count(repo,prices)==600
    assert repo.read_history('AAPL',NOW)['prices'].Date.iloc[0]==data.Date.iloc[-600]


def test_profile_fresh_reuse_and_failed_refresh_preserves_previous():
    from dashboard.market import get_profile
    db=MagicMock()
    db.read_profile.return_value={'symbol':'AAPL','name':'Apple','overview':'Saved text','profile_stale':False}
    get_profile.clear()
    with patch('dashboard.market.get_store',return_value=db),patch('dashboard.market.yf.Ticker') as api:
        assert get_profile('AAPL')['overview']=='Saved text'
        api.assert_not_called()
        get_profile.clear()
        db.read_profile.return_value['profile_stale']=True
        api.return_value.get_info.side_effect=RuntimeError('private detail')
        result=get_profile('AAPL')
        assert result['overview']=='Saved text' and result['profile_stale']
        db.save_profile.assert_not_called()
    get_profile.clear()
