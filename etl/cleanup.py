"""Explicit, scoped cleanup of saved stock prices. No scheduled deletion."""
import re
from sqlalchemy import bindparam, create_engine, inspect, text

PRICE_COLUMNS = {'date', 'open', 'high', 'low', 'close', 'volume'}


def eligible_tables(conn, legacy_names):
    inspector = inspect(conn)
    allowed = set(legacy_names) | {'stocks'}
    tables = []
    for name in inspector.get_table_names(schema='public'):
        if name not in allowed and not re.fullmatch(r'prices_[a-f0-9]{12}', name):
            continue
        columns = inspector.get_columns(name, schema='public')
        by_lower = {column['name'].lower(): column['name'] for column in columns}
        if PRICE_COLUMNS.issubset(by_lower):
            tables.append({'table': name, 'date_column': by_lower['date']})
    return sorted(tables, key=lambda row: row['table'])


def list_price_tables(database_url, legacy_names):
    engine = create_engine(database_url, connect_args={'connect_timeout': 5})
    try:
        with engine.connect() as conn:
            return eligible_tables(conn, legacy_names)
    finally:
        engine.dispose()


def delete_price_rows(database_url, legacy_names, selected, before=None):
    if not selected or len(selected) > 50 or len(selected) != len(set(selected)):
        raise ValueError('Select between 1 and 50 distinct price tables.')
    engine = create_engine(database_url, connect_args={'connect_timeout': 5})
    try:
        # Recheck table scope and columns inside the same transaction as deletion.
        # RESTRICT/default DELETE preserves tables and never drops dependent objects.
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout = '3s'"))
            conn.execute(text("SET LOCAL statement_timeout = '15s'"))
            available = {row['table']: row for row in eligible_tables(conn, legacy_names)}
            if not set(selected).issubset(available):
                raise ValueError('The selected tables changed or are outside the stock-export scope. Refresh the list.')
            quote = conn.dialect.identifier_preparer.quote_identifier
            # Hold locks through commit so dependencies cannot be added between check and DELETE.
            targets = ', '.join(f'{quote("public")}.{quote(name)}' for name in sorted(selected))
            conn.execute(text(f'LOCK TABLE {targets} IN SHARE ROW EXCLUSIVE MODE'))
            dependencies = text('''
                SELECT 1 FROM pg_catalog.pg_constraint c
                JOIN pg_catalog.pg_class t ON t.oid = c.confrelid
                JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
                WHERE c.contype = 'f' AND n.nspname = 'public' AND t.relname IN :tables
                UNION ALL
                SELECT 1 FROM pg_catalog.pg_trigger g
                JOIN pg_catalog.pg_class t ON t.oid = g.tgrelid
                JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
                WHERE NOT g.tgisinternal AND n.nspname = 'public' AND t.relname IN :tables
                LIMIT 1
            ''').bindparams(bindparam('tables', expanding=True))
            if conn.execute(dependencies, {'tables': selected}).first() is not None:
                raise ValueError('A selected price table has dependent foreign keys or custom triggers. Cleanup is blocked to avoid changing related data.')
            deleted = {}
            for name in selected:
                sql = f'DELETE FROM {quote("public")}.{quote(name)}'
                params = {}
                if before is not None:
                    sql += f' WHERE {quote(available[name]["date_column"])} < :before'
                    params['before'] = before
                deleted[name] = conn.execute(text(sql), params).rowcount
            return deleted
    finally:
        engine.dispose()
