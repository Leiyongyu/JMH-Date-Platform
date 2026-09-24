import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.ebay_api import accounts, workbook_accounts as module, EbayApiError
from backend.services import ebay_store_listing_sync_service as sync
from backend.repositories import ebay_store_listing_repository as repo
from backend.api import deps
from backend.api.v1 import internal_scheduler as api

SECRET = 'private-refresh-do-not-log'
HEAD = ['序号', '店铺名称', '平台', '店铺账号', 'browserId', '秘钥']


@pytest.fixture
def workbook(monkeypatch):
    monkeypatch.setenv('EBAY_SELLER_ACCOUNTS_FILE', 'data/test.xlsx')
    monkeypatch.setenv('EBAY_SELLER_ACCOUNTS_SHEET', '紫鸟店铺')
    monkeypatch.setenv('EBAY_SELLER_TOKEN_EXPIRES_ON', '2028-03-18')
    monkeypatch.setenv('EBAY_CLIENT_ID', 'test-id')
    monkeypatch.setenv('EBAY_CLIENT_SECRET', 'test-secret')
    def install(rows, head=None):
        values = [head or HEAD] + rows
        sheet = SimpleNamespace(max_row=len(values), max_column=len(values[0]),
            iter_rows=lambda: iter([tuple(SimpleNamespace(value=v, data_type='s') for v in row) for row in values]))
        book = MagicMock()
        book.sheetnames = ['紫鸟店铺']
        book.__getitem__.return_value = sheet
        monkeypatch.setattr(module, 'load_workbook', lambda *a, **kw: book)
        return book
    return install


def row(token=SECRET, platform='eBay-德国', browser='b1'):
    return [1, 'Shop A', platform, 'login@example.invalid', browser, token]


def test_only_ebay_with_token_and_credentials_repr_hidden(workbook):
    book = workbook([row(), row(None, browser='b2'), row('other-platform-secret', platform='亚马逊', browser='b3')])
    source = module.read_workbook_accounts()
    assert len(source['accounts']) == 1 and len(source['missing_credentials']) == 1 and source['ebay_rows'] == 2
    account = source['accounts'][0]
    assert accounts.credentials_for(account).refresh_token == SECRET
    assert SECRET not in repr(source)
    assert account['expires_on'] == date(2028, 3, 18)
    assert account['remind_on'] == date(2028, 2, 18)
    book.close.assert_called_once()


@pytest.mark.parametrize('today,status', [(date(2028,2,17),'VALID'), (date(2028,2,18),'EXPIRING'),
                                       (date(2028,3,17),'EXPIRING'), (date(2028,3,18),'EXPIRED')])
def test_calendar_month_boundary_and_no_token_in_report(workbook, today, status):
    workbook([row()])
    result = module.credential_expiry_report(today)
    assert result['accounts'][0]['status'] == status
    assert SECRET not in json.dumps(result) and 'test-secret' not in json.dumps(result)


def test_missing_dates_not_assumed_today(workbook, monkeypatch):
    workbook([row()])
    monkeypatch.setenv('EBAY_SELLER_TOKEN_EXPIRES_ON', '')
    result = module.credential_expiry_report(date(2026,9,19))
    assert result['accounts'][0]['status'] == 'UNKNOWN_EXPIRY'
    assert result['accounts'][0]['expires_on'] is None


def test_explicit_excel_date_overrides_batch_default(workbook):
    head = HEAD[:-1] + ['授权日期', '到期日期', '秘钥']
    workbook([row()[:-1] + ['2026-09-19', '2028-02-01', SECRET]], head)
    assert module.read_workbook_accounts()['accounts'][0]['expires_on'] == date(2028,2,1)


def test_authorized_date_plus_18_calendar_months(workbook):
    head = HEAD[:-1] + ['授权日期', '秘钥']
    workbook([row()[:-1] + ['2026-08-31', SECRET]], head)
    a = module.read_workbook_accounts()['accounts'][0]
    assert a['expires_on'] == date(2028,2,29)
    assert a['remind_on'] == date(2028,1,29)


@pytest.mark.parametrize('rows', [[row(), row(browser='b2')], [row(), row('other')], [row(1234)], [row(None)]])
def test_invalid_or_empty_configuration_fails_without_secrets(workbook, rows):
    workbook(rows)
    with pytest.raises(EbayApiError) as e:
        module.read_workbook_accounts()
    assert SECRET not in str(e.value)


def test_excel_source_takes_precedence_over_old_json(workbook, monkeypatch):
    workbook([row()])
    monkeypatch.setenv('EBAY_SELLER_ACCOUNTS', 'not valid json')
    assert len(accounts.configured_accounts()) == 1


def test_identity_not_login_email_is_used_and_no_secret_persisted(workbook, monkeypatch):
    workbook([row()])
    client = MagicMock()
    identity = {'username':'real-seller','userId':'stable-id'}
    client.trading_identity.return_value = identity
    client.active_listings_page.return_value = {'seller':identity,'ack':'Success','total_entries':1,'total_pages':1,
        'items':[{'item_id':'1','raw_xml':'<Item/>','current_price':{'value':None,'currency':None},
                  'buy_it_now_price':{'value':None,'currency':None}}]}
    monkeypatch.setattr(sync, 'EbaySellerClient', lambda c:client)
    saved=[]
    def replace(records, completed, **kwargs):
        saved.extend(records)
        return {'ods_rows':len(saved)}
    monkeypatch.setattr(repo,'replace_snapshots',replace)
    assert sync.sync_ebay_store_listings()['ods_rows'] == 1
    client.identity.assert_not_called()
    client.trading_identity.assert_called_once_with(expected_login='login@example.invalid')
    assert client.active_listings_page.call_args.kwargs['identity_source'] == 'trading'
    assert client.active_listings_page.call_args.kwargs['expected_username'] == 'real-seller'
    assert saved[0]['meta']['source_shop']['shop_name'] == 'Shop A'
    assert SECRET not in json.dumps(saved)


def test_expiry_endpoint_requires_internal_token(workbook, monkeypatch):
    workbook([row()])
    monkeypatch.setattr(deps,'settings',SimpleNamespace(python_internal_api_token='internal-test'))
    app=FastAPI()
    @app.middleware('http')
    async def trace(request,call_next):
        request.state.request_id='test'
        return await call_next(request)
    app.include_router(api.router)
    with TestClient(app) as client:
        url='/api/v1/internal/scheduler/ebay-credentials/expiry'
        assert client.get(url).status_code==401
        response=client.get(url,headers={'X-Internal-Token':'internal-test'})
        assert response.status_code==200 and SECRET not in response.text
