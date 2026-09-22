from contextlib import contextmanager
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from backend.ebay_api.credentials import EbayCredentials
from backend.ebay_api.health import HealthClient
from backend.services import ebay_token_health_service as service
from backend.services import scheduler_service as scheduler
from backend.repositories import ebay_token_health_repository as repository

SECRET = 'do-not-print-refresh-secret'


def response(status=200, payload=None, xml=''):
    result = MagicMock(status_code=status, content=xml.encode())
    result.json.return_value = payload
    return result


def xml_response(call, body='', ack='Success'):
    return response(xml=f'<{call}Response xmlns="urn:ebay:apis:eBLBaseComponents"><Ack>{ack}</Ack>{body}</{call}Response>')


def user(name='store', email='email@example.com'):
    return xml_response('GetUser', f'<User><UserID>{name}</UserID><Email>{email}</Email></User>')


def count(value='100'):
    return xml_response('GetMyeBaySelling', '<ActiveList><PaginationResult><TotalNumberOfEntries>'
        + value + '</TotalNumberOfEntries></PaginationResult></ActiveList>')


def probe(responses, expected='store'):
    session, pause = MagicMock(), MagicMock()
    session.post.side_effect = responses
    client = HealthClient(EbayCredentials('app', 'secret', SECRET), session=session, sleep=pause)
    return client.check(expected), session, pause


def token():
    return response(payload={'access_token': 'private-access-token'})


def test_success_uses_trading_not_identity_and_one_listing():
    result, session, pause = probe([token(), user(), count()])
    assert result == {'status': 'HEALTHY', 'reason': 'OK', 'seller_account': 'store', 'listing_count': 100}
    assert session.post.call_count == 3
    args = session.post.call_args_list[-1].kwargs
    assert b'<EntriesPerPage>1</EntriesPerPage>' in args['data']
    assert args['verify'] is True and args['allow_redirects'] is False
    assert all('identity/v1/user' not in c.kwargs['url'] for c in session.post.call_args_list)
    pause.assert_not_called()
    assert SECRET not in str(result) and 'email@example.com' not in str(result)


@pytest.mark.parametrize('status,payload,expected', [
    (400, {'error': 'invalid_grant'}, 'INVALID'),
    (401, {'error': 'invalid_grant'}, 'REVIEW'),
    (403, {'error': 'invalid_grant'}, 'REVIEW'),
    (400, {'error_description': 'invalid_grant'}, 'REVIEW'),
    (400, {'error': 'invalid_client'}, 'REVIEW'),
    (429, {}, 'REVIEW'), (500, {}, 'REVIEW'), (200, {}, 'REVIEW'),
])
def test_only_exact_oauth_invalid_grant_is_invalid(status, payload, expected):
    result, session, pause = probe([response(status, payload)])
    assert result['status'] == expected
    assert session.post.call_count == 1
    pause.assert_not_called()


def test_network_retries_bounded_and_redacted():
    error = requests.ConnectionError('URL?refresh_token=' + SECRET)
    result, session, pause = probe([error, error, error])
    assert session.post.call_count == 3
    assert [c.args[0] for c in pause.call_args_list] == [5, 15]
    assert result['status'] == 'REVIEW' and SECRET not in str(result)


def test_tls_not_retried_and_transient_recovery():
    result, session, pause = probe([requests.exceptions.SSLError(SECRET)])
    assert session.post.call_count == 1 and result['status'] == 'REVIEW'
    result, session, pause = probe([requests.Timeout(SECRET), token(), user(), count()])
    assert result['status'] == 'HEALTHY' and session.post.call_count == 4


@pytest.mark.parametrize('expected,identity,status', [
    ('STORE', user(), 'HEALTHY'), ('email@example.com', user(), 'HEALTHY'),
    ('wrong', user(), 'MISMATCH'), ('', user(), 'REVIEW'),
    ('email@example.com', user(email=''), 'REVIEW'),
    ('other@example.com', user(), 'MISMATCH'),
])
def test_identity_checked_before_count(expected, identity, status):
    result, session, pause = probe([token(), identity, count()], expected)
    assert result['status'] == status
    assert session.post.call_count == (3 if status == 'HEALTHY' else 2)


@pytest.mark.parametrize('bad', [
    response(xml='<truncated'), response(xml='<!DOCTYPE x><GetUserResponse/>'),
    response(xml='<GetUserResponse><Ack>Success</Ack></GetUserResponse>'),
    xml_response('GetUser', '<Errors><ErrorCode>931</ErrorCode><LongMessage>' + SECRET + '</LongMessage></Errors>', 'Failure'),
    xml_response('GetUser', ack='Warning'), response(403),
])
def test_xml_and_api_error_not_invalid_or_logged(bad):
    result, session, pause = probe([token(), bad])
    assert result['status'] == 'REVIEW' and SECRET not in str(result)


@pytest.mark.parametrize('value', ['', '-1', '1.5', 'nan', '１２', '100000000000000'])
def test_count_missing_or_invalid_not_silent_zero(value):
    result, _, _ = probe([token(), user(), count(value)])
    assert result['status'] == 'REVIEW' and result['listing_count'] is None


def source(n=1):
    return {'accounts': [{'source_row': 21+i, 'shop_name': f'Shop{i}', 'browser_id': str(i),
        'source_login': f'store{i}', '_credentials': 'not-serialized',
        'expires_on': date(2028, 3, 18), 'remind_on': date(2028, 2, 18)} for i in range(n)], 'missing_credentials': [{}]*4}


def results(counts):
    return [{'status': 'HEALTHY', 'reason': 'OK', 'seller_account': f'store{i}', 'listing_count': c} for i,c in enumerate(counts)]


def report(counts, previous=None, result_rows=None):
    values = iter(result_rows or results(counts))
    factory = lambda _: SimpleNamespace(check=lambda expected: next(values), close=lambda: None)
    return service.build_report(source(len(counts)), previous or {}, client_factory=factory, pause=lambda _: None,
                                now=datetime(2026, 9, 30, 9))


@pytest.mark.parametrize('current,before,status', [(0,None,'SUSPICIOUS'), (1,None,'HEALTHY'),
    (50,100,'SUSPICIOUS'), (51,100,'HEALTHY'), (200,100,'HEALTHY')])
def test_count_comparison(current,before,status):
    old = {} if before is None else {'0': {'seller_account': 'store0', 'listing_count': before}}
    assert report([current], old)['accounts'][0]['status'] == status


def test_account_change_does_not_compare_other_sellers_count():
    assert report([10], {'0': {'seller_account': 'other', 'listing_count': 1000}})['accounts'][0]['previous_count'] is None


def test_duplicate_identity_marks_both_and_never_becomes_baseline():
    data = results([10,10]); data[1]['seller_account'] = 'STORE0'
    assert [r['status'] for r in report([10,10], result_rows=data)['accounts']] == ['MISMATCH','MISMATCH']


def test_one_unexpected_failure_does_not_abort_others_or_leak():
    calls = []
    def factory(_):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError(SECRET)
        return SimpleNamespace(check=lambda _: results([2,3])[1], close=lambda: None)
    data = service.build_report(source(2), {}, client_factory=factory, pause=lambda _: None)
    assert [r['status'] for r in data['accounts']] == ['REVIEW', 'HEALTHY']
    assert SECRET not in str(data) and '_credentials' not in str(data)
    assert data['skipped_rows'] == 4


def test_repository_transaction_only_trusted_observations(monkeypatch):
    connection = MagicMock()
    @contextmanager
    def database():
        yield connection
    monkeypatch.setattr(repository, 'db_connection', database)
    data = results([10,0]); data.append({'status':'INVALID','reason':'OAUTH_INVALID_GRANT','seller_account':None,'listing_count':None})
    value = report([10,0,0], result_rows=data)
    repository.save_report(value)
    calls = connection.cursor.return_value.__enter__.return_value.execute.call_args_list
    assert len(calls) == 3 # report + healthy + suspicious; invalid does not overwrite baseline
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    connection.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError('db')
    with pytest.raises(RuntimeError): repository.save_report(value)
    connection.rollback.assert_called_once()


def test_scheduler_dispatch_and_date_rejection(monkeypatch):
    entered = []
    @contextmanager
    def lock(name):
        entered.append(name); yield True
    @contextmanager
    def database(): yield MagicMock()
    monkeypatch.setattr(scheduler.repo, 'named_lock', lock)
    monkeypatch.setattr(scheduler.repo, 'performance_connection', database)
    monkeypatch.setattr(scheduler.repo, 'insert_scheduler_run', MagicMock())
    fn = MagicMock(return_value=report([1]))
    monkeypatch.setattr(scheduler, 'check_ebay_token_health', fn)
    assert scheduler.run_scheduler_task(service.TASK_CODE)['status'] == 'completed'
    assert entered == ['ebay:token-health:check']
    fn.assert_called_once()
    with pytest.raises(ValueError): scheduler.run_scheduler_task(service.TASK_CODE, stat_month='2026-08')
