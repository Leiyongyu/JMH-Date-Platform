import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from backend.ebay_api import EbayApiError
from backend.ebay_api import accounts as config
from backend.services import ebay_store_listing_sync_service as service
from backend.repositories import ebay_store_listing_repository as repo


@pytest.fixture(autouse=True)
def isolate_workbook_environment(monkeypatch):
    monkeypatch.setenv('EBAY_SELLER_ACCOUNTS_FILE', '')


def account(name='shop-a', uid='user-a'):
    return {'username': name, 'user_id': uid, 'refresh_token_env': 'EBAY_TOKEN_A'}


def page(ids, total=None, pages=1, name='shop-a', uid='user-a'):
    return {'seller': {'username': name, 'userId': uid}, 'total_entries': len(ids) if total is None else total,
            'total_pages': pages, 'ack': 'Success', 'items': [
                {'item_id': i, 'sku': 'SAME-SKU', 'current_price': {'value': '12.3400', 'currency': 'EUR'},
                 'buy_it_now_price': {'value': None, 'currency': None}, 'raw_xml': '<Item><Future>x</Future></Item>'}
                for i in ids]}


def setup(monkeypatch, responses, accounts=None):
    monkeypatch.setattr(service, 'configured_accounts', lambda: accounts or [account()])
    monkeypatch.setattr(service, 'credentials_for', lambda a: object())
    client = MagicMock()
    client.active_listings_page.side_effect = responses
    monkeypatch.setattr(service, 'EbaySellerClient', lambda c: client)
    captured = []
    def publish(records, accounts, **kwargs):
        captured.extend(records)
        return {'ods_rows': len(captured), 'inserted_rows': len(captured), 'deleted_rows': 0}
    replace = MagicMock(side_effect=publish)
    monkeypatch.setattr(repo, 'replace_snapshots', replace)
    return client, replace, captured


def test_two_accounts_same_item_and_sku_kept_separate(monkeypatch):
    client, replace, records = setup(monkeypatch, [page(['1', '2']), page(['1'], name='b', uid='b')], [account(), account('b', 'b')])
    result = service.sync_ebay_store_listings()
    assert result['shop_count'] == 2 and result['ods_rows'] == 3
    assert [r['seller']['userId'] for r in records] == ['user-a', 'user-a', 'b']
    replace.assert_called_once()
    assert client.close.call_count == 2
    values = dict(zip(repo.FIELDS, repo.record_values(records[0], 'batch', datetime.now()), strict=True))
    assert values['current_price'] == '12.3400' and values['quantity_sold'] is None
    assert '<Future>x</Future>' in values['raw_xml']


def test_all_pages_and_final_short_page(monkeypatch):
    monkeypatch.setattr(service, 'PAGE_SIZE', 2)
    client, _, records = setup(monkeypatch, [page(['1', '2'], 3, 2), page(['3'], 3, 2)])
    assert service.sync_ebay_store_listings()['ods_rows'] == 3
    assert [c.kwargs['page'] for c in client.active_listings_page.call_args_list] == [1, 2]
    assert len(records) == 3


@pytest.mark.parametrize('second', [page(['1'], 2, 2), page(['2'], 3, 3), page([], 2, 2),
                                   page(['2'], 2, 2, uid='wrong'), RuntimeError('secret-token')])
def test_failure_keeps_old_snapshot(monkeypatch, second):
    monkeypatch.setattr(service, 'PAGE_SIZE', 1)
    client, replace, _ = setup(monkeypatch, [page(['1'], 2, 2), second])
    with pytest.raises(service.EbayStoreListingSyncError) as error:
        service.sync_ebay_store_listings()
    assert 'secret-token' not in str(error.value)
    replace.assert_not_called()
    client.close.assert_called_once()


def test_second_account_failure_does_not_publish_first(monkeypatch):
    _, replace, _ = setup(monkeypatch, [page(['1']), EbayApiError('identity mismatch')], [account(), account('b', 'b')])
    with pytest.raises(service.EbayStoreListingSyncError):
        service.sync_ebay_store_listings()
    replace.assert_not_called()


@pytest.mark.parametrize('response', [{**page(['1']), 'ack': 'Warning'}, page(['1'], 101, 1), page(['1'], 2, 1)])
def test_warning_inconsistent_page_count_or_short_page_never_published(monkeypatch, response):
    _, replace, _ = setup(monkeypatch, [response])
    with pytest.raises(service.EbayStoreListingSyncError):
        service.sync_ebay_store_listings()
    replace.assert_not_called()


@pytest.mark.parametrize('pages', [0, 1])
def test_explicit_zero_store_can_publish_empty(monkeypatch, pages):
    _, replace, _ = setup(monkeypatch, [page([], 0, pages)])
    assert service.sync_ebay_store_listings()['ods_rows'] == 0
    assert replace.call_args.args[1][0]['row_count'] == 0


@pytest.mark.parametrize('value', ['[]', '{}', 'bad-json', json.dumps([account(), account()]),
    json.dumps([{**account(), 'token_file': 'somewhere'}]), json.dumps([{**account(), 'refresh_token': 'secret'}])])
def test_reject_invalid_account_configuration(monkeypatch, value):
    monkeypatch.setenv('EBAY_SELLER_ACCOUNTS', value)
    with pytest.raises(EbayApiError) as error:
        config.configured_accounts()
    assert 'secret' not in str(error.value)


def test_account_credentials_never_fall_back_to_other_store(monkeypatch):
    monkeypatch.setenv('EBAY_CLIENT_ID', 'id')
    monkeypatch.setenv('EBAY_CLIENT_SECRET', 'secret')
    monkeypatch.setenv('EBAY_REFRESH_TOKEN', 'other-store')
    monkeypatch.delenv('EBAY_TOKEN_A', raising=False)
    with pytest.raises(EbayApiError):
        config.credentials_for(account())


def db(monkeypatch):
    connection, cursor = MagicMock(), MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr(repo, 'db_connection', lambda: context)
    cursor.fetchone.return_value = {'n': 1}
    cursor.rowcount = 1
    response = page(['1'])
    record = {'seller': response['seller'], 'item': response['items'][0], 'page': 1, 'total': 1, 'meta': {}}
    accounts = [{**response['seller'], 'row_count': 1, 'published_at': datetime.now()}]
    return connection, cursor, record, accounts


def test_delete_scoped_to_stable_account_and_commit_state_together(monkeypatch):
    connection, cursor, record, accounts = db(monkeypatch)
    repo.replace_snapshots([record], accounts, batch_id='b', pulled_at=datetime.now())
    delete = [c for c in cursor.execute.call_args_list if c.args[0].startswith('DELETE')]
    assert len(delete) == 1 and delete[0].args == (f'DELETE FROM {repo.TABLE} WHERE seller_user_id=%s', ('user-a',))
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()


@pytest.mark.parametrize('conflict_at', [1, 2])
def test_trading_id_conflict_checked_in_both_tables_before_any_delete(monkeypatch, conflict_at):
    connection, cursor, record, accounts = db(monkeypatch)
    accounts[0]['userId'] = 'trading:' + 'a' * 64
    record['seller']['userId'] = accounts[0]['userId']
    cursor.fetchone.side_effect = [None] * (conflict_at - 1) + [{'seller_user_id':'legacy-rest-id'}]
    with pytest.raises(repo.AccountIdentityConflict, match='未删除'):
        repo.replace_snapshots([record], accounts, batch_id='b', pulled_at=datetime.now())
    assert not any(c.args[0].startswith('DELETE') for c in cursor.execute.call_args_list)
    cursor.executemany.assert_not_called()
    connection.rollback.assert_called_once()


def test_new_trading_id_publishes_after_no_conflicts(monkeypatch):
    connection, cursor, record, accounts = db(monkeypatch)
    accounts[0]['userId'] = 'trading:' + 'a' * 64
    record['seller']['userId'] = accounts[0]['userId']
    cursor.fetchone.side_effect = [None, None, {'n':1}]
    assert repo.replace_snapshots([record], accounts, batch_id='b', pulled_at=datetime.now())['ods_rows'] == 1
    connection.commit.assert_called_once()


@pytest.mark.parametrize('failure', ['insert', 'count', 'wrong_account', 'missing_record'])
def test_repository_rolls_back_every_failure(monkeypatch, failure):
    connection, cursor, record, accounts = db(monkeypatch)
    if failure == 'insert':
        cursor.executemany.side_effect = RuntimeError('db error')
    if failure == 'count':
        cursor.fetchone.return_value = {'n': 0}
    if failure == 'wrong_account':
        record['seller'] = {'userId': 'unexpected', 'username': 'b'}
    with pytest.raises((RuntimeError, ValueError)):
        repo.replace_snapshots([] if failure == 'missing_record' else [record], accounts, batch_id='b', pulled_at=datetime.now())
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
