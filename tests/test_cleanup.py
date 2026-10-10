from unittest.mock import MagicMock, patch
from datetime import date
import pytest
from sqlalchemy.dialects.postgresql import dialect
from etl.cleanup import eligible_tables, list_price_tables, delete_price_rows
from streamlit.testing.v1 import AppTest
from pathlib import Path


def inspector():
    obj = MagicMock()
    obj.get_table_names.return_value = ['aapl','users','stocks','prices_123456abcdef','msft','aapl;drop users']
    obj.get_columns.side_effect = lambda name, **kw: [{'name':col} for col in
        (['Date','Open','High','Low','Close','Volume'] if name != 'msft' else ['id'])]
    obj.get_foreign_keys.return_value = []
    return obj


def connection():
    conn = MagicMock()
    conn.dialect = dialect()
    conn.execute.return_value.rowcount = 12
    conn.execute.return_value.first.return_value = None
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    engine.connect.return_value.__enter__.return_value = conn
    return engine, conn


def test_inventory_excludes_unrelated_tables_and_checks_price_columns():
    with patch('etl.cleanup.inspect',return_value=inspector()):
        rows = eligible_tables(MagicMock(), {'aapl','msft'})
    assert [row['table'] for row in rows] == ['aapl','prices_123456abcdef','stocks']


@pytest.mark.parametrize('cutoff', [None, date(2025,1,1)])
def test_manual_cleanup_scope_quotes_cutoff_and_disposal(cutoff):
    engine, conn = connection()
    with patch('etl.cleanup.create_engine',return_value=engine), patch('etl.cleanup.inspect',return_value=inspector()):
        assert delete_price_rows('postgresql://placeholder',{'aapl'},['aapl'],before=cutoff) == {'aapl':12}
    sql = str(conn.execute.call_args.args[0])
    assert sql.startswith('DELETE FROM "public"."aapl"')
    assert ('WHERE "Date" < :before' in sql) == (cutoff is not None)
    assert conn.execute.call_args.args[1] == ({'before':cutoff} if cutoff else {})
    engine.dispose.assert_called_once()


def test_unlisted_table_cannot_be_deleted_and_transaction_rolls_back():
    engine, conn = connection()
    with patch('etl.cleanup.create_engine',return_value=engine), patch('etl.cleanup.inspect',return_value=inspector()):
        with pytest.raises(ValueError): delete_price_rows('postgresql://placeholder',{'aapl'},['users'])
    assert not any(str(call.args[0]).startswith('DELETE') for call in conn.execute.call_args_list)
    assert engine.begin.return_value.__exit__.call_args.args[0] == ValueError
    engine.dispose.assert_called_once()


def test_foreign_key_dependents_block_deletion():
    engine, conn = connection()
    obj=inspector();conn.execute.return_value.first.return_value = (1,)
    with patch('etl.cleanup.create_engine',return_value=engine), patch('etl.cleanup.inspect',return_value=obj):
        with pytest.raises(ValueError,match='dependent'): delete_price_rows('postgresql://placeholder',{'aapl'},['aapl'])
    assert not any(str(call.args[0]).startswith('DELETE') for call in conn.execute.call_args_list)


def test_inventory_releases_connection_after_failure():
    engine, conn = connection()
    with patch('etl.cleanup.create_engine',return_value=engine), patch('etl.cleanup.inspect',side_effect=RuntimeError):
        with pytest.raises(RuntimeError): list_price_tables('postgresql://placeholder',{'aapl'})
    engine.dispose.assert_called_once()


def ui():
    # Import helper via a temporary app source; no provider/API/database network calls.
    return AppTest.from_string('from dashboard.database_admin import render_cleanup\nrender_cleanup({"AAPL":{}})')


def item(items,label): return next(row for row in items if row.label==label)


def test_cleanup_locked_by_default_and_wrong_password_never_connects():
    with patch('dashboard.database_admin.setting',return_value=''), patch('etl.cleanup.list_price_tables') as listing:
        at=ui().run();assert not at.exception
        assert any('locked' in info.value for info in at.info)
        listing.assert_not_called()
    settings={'DATABASE_ADMIN_TOKEN':'a-long-secret-only-for-tests','DATABASE_URL':'postgresql://placeholder'}
    with patch('dashboard.database_admin.setting',side_effect=lambda key:settings.get(key,'')), patch('etl.cleanup.list_price_tables') as listing:
        at=ui().run()
        item(at.text_input,'Database administrator password').set_value('wrong')
        item(at.button,'Unlock database cleanup').click().run()
        assert not at.exception
        assert any('did not match' in row.value for row in at.warning)
        listing.assert_not_called()


def test_authenticated_cleanup_requires_confirmation_and_supports_new_rows():
    settings={'DATABASE_ADMIN_TOKEN':'a-long-secret-only-for-tests','DATABASE_URL':'postgresql://placeholder'}
    with patch('dashboard.database_admin.setting',side_effect=lambda key:settings.get(key,'')), \
         patch('etl.cleanup.list_price_tables',return_value=[{'table':'aapl','date_column':'Date'}]) as listing, \
         patch('etl.cleanup.delete_price_rows',return_value={'aapl':12}) as delete:
        at=ui().run()
        item(at.text_input,'Database administrator password').set_value(settings['DATABASE_ADMIN_TOKEN'])
        item(at.button,'Unlock database cleanup').click().run()
        assert not at.exception
        listing.assert_not_called();delete.assert_not_called()
        item(at.button,'Refresh saved price tables').click().run()
        item(at.multiselect,'Saved price tables').set_value(['aapl'])
        item(at.radio,'Rows to delete').set_value('All rows (old and new)')
        item(at.button,'Delete selected saved rows').click().run()
        delete.assert_not_called()
        item(at.text_input,'Type DELETE to confirm').set_value('DELETE')
        item(at.checkbox,'I understand this permanently deletes the selected saved rows.').check()
        item(at.button,'Delete selected saved rows').click().run()
        assert not at.exception
        delete.assert_called_once_with('postgresql://placeholder',{'aapl'},['aapl'],before=None)
        assert any('aapl: 12' in row.value for row in at.success)


def test_expired_or_changed_credentials_lock_the_ui():
    settings={'DATABASE_ADMIN_TOKEN':'a-long-secret-only-for-tests','DATABASE_URL':'postgresql://placeholder'}
    with patch('dashboard.database_admin.setting',side_effect=lambda key:settings.get(key,'')), patch('etl.cleanup.list_price_tables') as listing:
        at=ui().run()
        item(at.text_input,'Database administrator password').set_value(settings['DATABASE_ADMIN_TOKEN'])
        item(at.button,'Unlock database cleanup').click().run()
        saved=dict(at.session_state['database_admin_auth'])
        at.session_state['database_admin_auth']={**saved,'at':float('-inf')}
        at.run()
        assert any(row.label=='Unlock database cleanup' for row in at.button)
        at.session_state['database_admin_auth']=saved
        settings['DATABASE_URL']='postgresql://different-database'
        at.run()
        assert any(row.label=='Unlock database cleanup' for row in at.button)
        listing.assert_not_called()
