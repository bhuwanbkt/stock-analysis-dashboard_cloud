"""Bounded shared price/profile/forecast store. Existing export tables are untouched."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import uuid
import pandas as pd
from sqlalchemy import (MetaData, Table, Column, String, Date, DateTime, Float,
                        BigInteger, Integer, Text, select, delete, update, func)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

MAX_COMPANIES = 50
MAX_FORECASTS = 5000
metadata = MetaData()
companies = Table('stock_companies', metadata,
    Column('symbol', String(15), primary_key=True), Column('profile', Text, nullable=False),
    Column('profile_updated_at', DateTime(timezone=True)))
prices = Table('stock_daily_prices', metadata,
    Column('symbol', String(15), primary_key=True), Column('Date', Date, primary_key=True),
    *[Column(name, Float, nullable=False) for name in ['Open','High','Low','Close']],
    Column('Volume', BigInteger, nullable=False))
refresh = Table('stock_refresh_status', metadata,
    Column('symbol', String(15), primary_key=True), Column('fetched_at', DateTime(timezone=True)),
    Column('downloaded_rows', Integer), Column('lease_until', DateTime(timezone=True)),
    Column('lease_token', String(36)),
    Column('retry_after', DateTime(timezone=True)))
forecasts = Table('stock_forecast_runs', metadata,
    Column('symbol', String(15), primary_key=True), Column('as_of', Date, primary_key=True),
    Column('horizon', Integer, primary_key=True), Column('model_version', String(40), primary_key=True),
    Column('created_at', DateTime(timezone=True), nullable=False), Column('result', Text, nullable=False),
    Column('realized_return', Float), Column('evaluated_at', DateTime(timezone=True)))
maintenance = Table('stock_maintenance', metadata,
    Column('key', String(40), primary_key=True), Column('last_run', DateTime(timezone=True)))


def utc(value):
    if value is None: return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def cutoff_date(now):
    return (pd.Timestamp(now) - pd.DateOffset(years=2)).date()


class SharedStore:
    def __init__(self, engine): self.engine = engine

    @contextmanager
    def transaction(self):
        with self.engine.begin() as conn:
            if conn.dialect.name == 'postgresql':
                from sqlalchemy import text
                conn.execute(text("SET LOCAL lock_timeout = '3s'"))
                conn.execute(text("SET LOCAL statement_timeout = '12s'"))
            yield conn

    def insert(self, table):
        return pg_insert(table) if self.engine.dialect.name == 'postgresql' else sqlite_insert(table)

    def initialize(self):
        with self.transaction() as conn:
            if conn.dialect.name == 'postgresql':
                from sqlalchemy import text
                conn.execute(text('SELECT pg_advisory_xact_lock(73419321)'))
            metadata.create_all(conn)
            for key in ['capacity', 'weekly_cleanup']:
                conn.execute(self.insert(maintenance).values(key=key).on_conflict_do_nothing())

    def capacity_lock(self, conn):
        conn.execute(select(maintenance.c.key).where(maintenance.c.key == 'capacity').with_for_update()).first()

    def ensure_company(self, conn, symbol, now=None):
        now=now or datetime.now(timezone.utc)
        if conn.execute(select(companies.c.symbol).where(companies.c.symbol == symbol)).first(): return True
        pending=conn.scalar(select(func.count()).select_from(refresh).where(refresh.c.symbol != symbol,
            refresh.c.symbol.not_in(select(companies.c.symbol)),refresh.c.lease_until > now))
        if conn.scalar(select(func.count()).select_from(companies)) + pending >= MAX_COMPANIES: return False
        seed = {'symbol':symbol,'name':symbol,'overview':None,'currency':None,
                'source':'Validated daily price history','updated_at':None}
        conn.execute(self.insert(companies).values(symbol=symbol, profile=json.dumps(seed)).on_conflict_do_nothing())
        return True

    def read_history(self, symbol, now=None):
        now = now or datetime.now(timezone.utc)
        with self.transaction() as conn:
            state = conn.execute(select(refresh).where(refresh.c.symbol == symbol)).mappings().first()
            rows = conn.execute(select(prices).where(prices.c.symbol == symbol,
                                prices.c.Date >= cutoff_date(now)).order_by(prices.c.Date)).mappings().all()
        if not rows or not state or not state['fetched_at']: return None
        frame = pd.DataFrame(rows).drop(columns=['symbol'])
        frame['Date'] = pd.to_datetime(frame['Date'])
        fetched = utc(state['fetched_at'])
        return {'prices':frame,'fetched_at':fetched.isoformat(),
                'downloaded_rows':state['downloaded_rows'], 'period':'2y',
                'source':'Postgres', 'persisted':True, 'stale': now-fetched >= timedelta(hours=24),
                'retry_after':utc(state['retry_after'])}

    def claim_refresh(self, symbol, now=None):
        now = now or datetime.now(timezone.utc)
        with self.transaction() as conn:
            self.capacity_lock(conn)
            # Failed unknown tickers must not become saved companies or grow the refresh table forever.
            conn.execute(delete(refresh).where(refresh.c.symbol.not_in(select(companies.c.symbol)),
                (refresh.c.lease_until.is_(None) | (refresh.c.lease_until <= now)),
                (refresh.c.retry_after.is_(None) | (refresh.c.retry_after <= now))))
            exists=conn.scalar(select(companies.c.symbol).where(companies.c.symbol == symbol))
            pending=conn.scalar(select(func.count()).select_from(refresh).where(refresh.c.symbol != symbol,
                refresh.c.symbol.not_in(select(companies.c.symbol)),refresh.c.lease_until > now))
            if not exists and (conn.scalar(select(func.count()).select_from(companies)) + pending >= MAX_COMPANIES
                               or conn.scalar(select(func.count()).select_from(refresh)) >= 100): return ('capacity',None)
            conn.execute(self.insert(refresh).values(symbol=symbol).on_conflict_do_nothing())
            row = conn.execute(select(refresh).where(refresh.c.symbol == symbol).with_for_update()).mappings().one()
            if utc(row['lease_until']) and utc(row['lease_until']) > now: return ('busy',None)
            if utc(row['retry_after']) and utc(row['retry_after']) > now: return ('backoff',None)
            # Another request may have refreshed between read_history and claiming this row.
            if utc(row['fetched_at']) and now-utc(row['fetched_at']) < timedelta(hours=24):
                if conn.scalar(select(func.count()).select_from(prices).where(prices.c.symbol == symbol,
                               prices.c.Date >= cutoff_date(now))) >= 2: return ('fresh',None)
            token=str(uuid.uuid4())
            conn.execute(update(refresh).where(refresh.c.symbol == symbol).values(
                lease_until=now+timedelta(minutes=3), lease_token=token, retry_after=None))
            return ('claimed',token)

    def finish_refresh(self, symbol, frame, downloaded_rows, token, now=None):
        now = now or datetime.now(timezone.utc)
        selected = frame.loc[frame.Date >= pd.Timestamp(cutoff_date(now))].tail(600)
        if len(selected) < 2:
            self.fail_refresh(symbol,token,now)
            return False
        records = [{'symbol':symbol,'Date':row.Date.date(), **{col:float(getattr(row,col)) for col in
                   ['Open','High','Low','Close']}, 'Volume':int(row.Volume)} for row in selected.itertuples()]
        with self.transaction() as conn:
            self.capacity_lock(conn)
            state=conn.execute(select(refresh).where(refresh.c.symbol == symbol).with_for_update()).mappings().first()
            if not state or state['lease_token'] != token: return False
            if not self.ensure_company(conn,symbol,now):
                conn.execute(update(refresh).where(refresh.c.symbol == symbol).values(lease_until=None,lease_token=None))
                return False
            # Daily downloads refresh the full two-year window so corporate-action revisions replace old values.
            if records:
                stmt = self.insert(prices).values(records)
                conn.execute(stmt.on_conflict_do_update(index_elements=['symbol','Date'],
                    set_={name:getattr(stmt.excluded,name) for name in ['Open','High','Low','Close','Volume']}))
            conn.execute(delete(prices).where(prices.c.symbol == symbol, prices.c.Date.not_in([r['Date'] for r in records])))
            conn.execute(update(refresh).where(refresh.c.symbol == symbol).values(
                fetched_at=now, downloaded_rows=downloaded_rows, lease_until=None, lease_token=None,retry_after=None))
            self.evaluate_forecasts(conn, symbol, selected, now)
            return True

    def fail_refresh(self, symbol, token, now=None):
        now = now or datetime.now(timezone.utc)
        with self.transaction() as conn:
            conn.execute(update(refresh).where(refresh.c.symbol == symbol,refresh.c.lease_token == token).values(
                lease_until=None,lease_token=None,retry_after=now+timedelta(minutes=5)))

    def catalog(self):
        with self.transaction() as conn:
            return {row.symbol:json.loads(row.profile) for row in conn.execute(select(companies)).all()}

    def read_profile(self, symbol, now=None):
        now = now or datetime.now(timezone.utc)
        with self.transaction() as conn:
            row = conn.execute(select(companies).where(companies.c.symbol == symbol)).mappings().first()
        if not row: return None
        profile = json.loads(row['profile'])
        profile['profile_stale'] = not row['profile_updated_at'] or now-utc(row['profile_updated_at']) >= timedelta(days=30)
        return profile

    def save_profile(self, symbol, profile, now=None):
        now = now or datetime.now(timezone.utc)
        with self.transaction() as conn:
            self.capacity_lock(conn)
            if not self.ensure_company(conn, symbol, now): return False
            old = json.loads(conn.scalar(select(companies.c.profile).where(companies.c.symbol == symbol)))
            old.update({key:value for key,value in profile.items() if value is not None})
            values={'profile':json.dumps(old)}
            if profile.get('overview'): values['profile_updated_at']=now
            conn.execute(update(companies).where(companies.c.symbol == symbol).values(**values))
            return True

    def record_forecast(self, symbol, result, version, now=None):
        if not result.get('available'): return False
        now = now or datetime.now(timezone.utc)
        with self.transaction() as conn:
            self.capacity_lock(conn)
            if not conn.scalar(select(companies.c.symbol).where(companies.c.symbol == symbol)): return False
            key=dict(symbol=symbol,as_of=pd.Timestamp(result['as_of']).date(),
                     horizon=result['horizon'],model_version=version)
            if conn.execute(select(forecasts.c.symbol).filter_by(**key)).first(): return True
            if conn.scalar(select(func.count()).select_from(forecasts)) >= MAX_FORECASTS: return False
            conn.execute(self.insert(forecasts).values(**key,created_at=now,result=json.dumps(result)).on_conflict_do_nothing())
            return True

    def evaluate_forecasts(self, conn, symbol, frame, now):
        rows = conn.execute(select(forecasts).where(forecasts.c.symbol == symbol,
                            forecasts.c.realized_return.is_(None))).mappings().all()
        daily = frame.set_index('Date')['Close'].sort_index()
        for row in rows:
            origin = pd.Timestamp(row['as_of'])
            if origin not in daily.index: continue
            later = daily.loc[daily.index > origin]
            if len(later) < row['horizon']: continue
            # Both endpoints use the SAME current adjustment basis; do not divide by an old adjusted-price snapshot.
            realized = float(later.iloc[row['horizon']-1] / daily.loc[origin] - 1)
            conn.execute(update(forecasts).where(forecasts.c.symbol == symbol,forecasts.c.as_of == row['as_of'],
                forecasts.c.horizon == row['horizon'],forecasts.c.model_version == row['model_version']).values(
                    realized_return=realized,evaluated_at=now))

    def forecast_history(self, symbol):
        with self.transaction() as conn:
            rows=conn.execute(select(forecasts).where(forecasts.c.symbol == symbol).order_by(
                              forecasts.c.created_at.desc()).limit(30)).mappings().all()
        return [{'Forecast date':str(row['as_of']),'Sessions ahead':row['horizon'],
                 'Method':json.loads(row['result'])['model'],
                 'Predicted return (%)':100*json.loads(row['result'])['predicted_return'],
                 'Observed return (%)':None if row['realized_return'] is None else 100*row['realized_return'],
                 'Status':'Pending' if row['realized_return'] is None else 'Evaluated'} for row in rows]

    def maintain(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self.transaction() as conn:
            row=conn.execute(select(maintenance).where(maintenance.c.key == 'weekly_cleanup').with_for_update()).mappings().one()
            if row['last_run'] and now-utc(row['last_run']) < timedelta(days=7): return False
            conn.execute(delete(prices).where(prices.c.Date < cutoff_date(now)))
            conn.execute(delete(forecasts).where(forecasts.c.created_at < now-timedelta(days=90)))
            conn.execute(update(maintenance).where(maintenance.c.key == 'weekly_cleanup').values(last_run=now))
            return True
