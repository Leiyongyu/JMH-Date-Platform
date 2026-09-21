import ssl
from unittest.mock import Mock

import pytest
import requests

from backend.ebay_api import EbayApiError, EbayCredentials, EbaySellerClient
from backend.ebay_api.listings import MissingActiveList, parse_active_page
from backend.services import ebay_store_listing_sync_service as service

SECRET = 'private-token-or-response-text'


def envelope(content='', ack='Success', errors=''):
    return (f'<GetMyeBaySellingResponse xmlns="urn:ebay:apis:eBLBaseComponents">'
            f'<Ack>{ack}</Ack>{errors}{content}</GetMyeBaySellingResponse>').encode()


def active(ids=('item1',), total=1, pages=1):
    items = ''.join(f'<Item><ItemID>{i}</ItemID><Title>{SECRET}</Title></Item>' for i in ids)
    return envelope(f'<ActiveList><PaginationResult><TotalNumberOfEntries>{total}</TotalNumberOfEntries>'
                    f'<TotalNumberOfPages>{pages}</TotalNumberOfPages></PaginationResult>'
                    f'<ItemArray>{items}</ItemArray></ActiveList>')


def warning(code='21917091', severity='Warning'):
    return f'<Errors><ErrorCode>{code}</ErrorCode><SeverityCode>{severity}</SeverityCode><LongMessage>{SECRET}</LongMessage></Errors>'


def client(responses):
    session, sleep = Mock(), Mock()
    session.request.side_effect = [r if isinstance(r, BaseException) else Mock(status_code=200, content=r)
                                   for r in responses]
    api = EbaySellerClient(EbayCredentials(SECRET, SECRET, SECRET), session=session, sleep=sleep)
    api.trading_identity = Mock(return_value={'username': 'shop', 'userId': 'u1'})
    api._access_token = Mock(return_value=SECRET)
    return api, session, sleep


def fetch(api, page=4, size=100):
    return api.active_listings_page(expected_username='shop', page=page, page_size=size)


@pytest.mark.parametrize('ack,retryable', [('Success', True), ('Warning', False)])
def test_missing_list_diagnostics_are_safe(ack, retryable):
    raw = envelope(ack=ack, errors=warning())
    with pytest.raises(MissingActiveList) as error:
        parse_active_page(raw, page=4, page_size=100)
    assert error.value.retryable is retryable
    msg = str(error.value)
    for value in (f'ack={ack}', 'warning_codes=21917091', 'page=4', 'page_size=100', f'response_bytes={len(raw)}'):
        assert value in msg
    assert SECRET not in msg


def test_success_missing_list_retries_identical_page(caplog):
    api, session, sleep = client([envelope(errors=warning()), active(total=301, pages=4)])
    result = fetch(api)
    assert result['returned_count'] == 1 and result['page'] == 4
    assert session.request.call_count == 2
    assert session.request.call_args_list[0] == session.request.call_args_list[1]
    request = session.request.call_args.kwargs
    assert b'<PageNumber>4</PageNumber>' in request['data']
    assert request['verify'] is True and request['allow_redirects'] is False
    assert 'response_parser' not in request
    sleep.assert_called_once_with(5)
    assert 'ack=Success' in caplog.text and 'request_attempt=1/3' in caplog.text
    assert SECRET not in caplog.text


def test_repeated_missing_list_fails_after_three_requests(caplog):
    api, session, sleep = client([envelope()] * 3)
    with pytest.raises(EbayApiError) as error:
        fetch(api)
    assert session.request.call_count == 3
    assert [c.args[0] for c in sleep.call_args_list] == [5, 15]
    assert 'request_attempt=3/3' in str(error.value) and 'page=4' in str(error.value)
    assert SECRET not in caplog.text + str(error.value)


@pytest.mark.parametrize('raw', [envelope(ack='Warning', errors=warning()),
    envelope(ack='Failure', errors=warning('931', 'Error')),
    envelope(ack='Success', errors=warning('931', 'Error')), b'<bad>', b'<html/>',
    envelope('<ActiveList/>')])
def test_other_invalid_responses_still_fail_without_retry(raw):
    api, session, sleep = client([raw, active()])
    with pytest.raises(EbayApiError):
        fetch(api)
    session.request.assert_called_once()
    sleep.assert_not_called()


def test_mixed_network_tls_and_missing_list_share_three_attempts():
    api, session, sleep = client([requests.Timeout(SECRET),
        requests.exceptions.SSLError(ssl.SSLEOFError(8, SECRET)), envelope(), active()])
    with pytest.raises(EbayApiError, match='request_attempt=3/3'):
        fetch(api)
    assert session.request.call_count == 3
    assert [c.args[0] for c in sleep.call_args_list] == [5, 15]


def test_valid_explicit_empty_list_is_not_retried():
    api, session, sleep = client([active(ids=(), total=0, pages=0)])
    assert fetch(api, page=1)['items'] == []
    session.request.assert_called_once()
    sleep.assert_not_called()


def wire_service(monkeypatch, api):
    monkeypatch.setattr(service, 'PAGE_SIZE', 1)
    monkeypatch.setattr(service, 'configured_accounts', lambda: [{'username': 'shop', 'user_id': 'u1'}])
    monkeypatch.setattr(service, 'credentials_for', lambda account: object())
    monkeypatch.setattr(service, 'EbaySellerClient', lambda _: api)
    monkeypatch.setattr(service.time, 'sleep', Mock())
    records = []
    def publish(rows, accounts, **kwargs):
        records.extend(rows)
        return {'ods_rows': len(records)}
    replace = Mock(side_effect=publish)
    monkeypatch.setattr(service.repo, 'replace_snapshots', replace)
    # The legacy test account uses REST identity; avoid all external calls.
    api.identity = api.trading_identity
    return replace, records


def test_recovered_page_total_change_still_restarts_account(monkeypatch):
    api, session, _ = client([active(('old',), 2, 2), envelope(), active(('changed',), 3, 3),
        active(('new1',), 3, 3), active(('new2',), 3, 3), active(('new3',), 3, 3)])
    replace, records = wire_service(monkeypatch, api)
    result = service.sync_ebay_store_listings()
    assert result['account_retries'] == 1 and result['extract_rows'] == result['ods_rows'] == 3
    assert [r['item']['item_id'] for r in records] == ['new1', 'new2', 'new3']
    import re
    assert [int(re.search(rb'<PageNumber>(\d+)</PageNumber>', c.kwargs['data'])[1])
            for c in session.request.call_args_list] == [1, 2, 2, 1, 2, 3]
    replace.assert_called_once()


def test_missing_page_exhaustion_never_publishes_or_advances(monkeypatch):
    api, session, _ = client([active(('old',), 2, 2), envelope(), envelope(), envelope()])
    replace, records = wire_service(monkeypatch, api)
    with pytest.raises(service.EbayStoreListingSyncError) as error:
        service.sync_ebay_store_listings()
    assert 'page=2' in str(error.value) and 'request_attempt=3/3' in str(error.value)
    assert error.value.metrics['ods_rows'] == 0
    assert session.request.call_count == 4
    replace.assert_not_called()
    assert records == []
