import errno
import ssl
from unittest.mock import Mock

import pytest
import requests
from urllib3.exceptions import MaxRetryError, SSLError as UrllibSSLError
from urllib3.util.ssl_match_hostname import CertificateError as HostnameMismatch

from backend.ebay_api import EbayApiError, EbayCredentials, EbaySellerClient
from backend.ebay_api.client import TOKEN_URL, TRADING_URL
from backend.ebay_api.tls import tls_failure

SECRET = 'private-token-signed-url-and-password'


def wrapped(inner):
    return requests.exceptions.SSLError(MaxRetryError(
        None, 'https://private.invalid/?token=' + SECRET, reason=UrllibSSLError(inner)))


def certificate():
    exc = ssl.SSLCertVerificationError(1, SECRET)
    exc.verify_code = 62
    exc.verify_message = SECRET
    exc.reason = 'CERTIFICATE_VERIFY_FAILED'
    exc.library = 'SSL'
    return exc


def reset():
    exc = OSError()
    exc.winerror = 10054
    return exc


@pytest.mark.parametrize('factory', [
    lambda: ssl.SSLEOFError(8, SECRET), lambda: ssl.SSLZeroReturnError(6, SECRET), reset,
    lambda: ConnectionResetError(errno.ECONNRESET, SECRET),
])
def test_wrapped_temporary_disconnect_is_safe_and_retryable(factory):
    retry, diagnostic = tls_failure(wrapped(factory()))
    assert retry and 'category=temporary_tls_disconnect' in diagnostic
    assert 'MaxRetryError' in diagnostic
    assert SECRET not in diagnostic and 'private.invalid' not in diagnostic


@pytest.mark.parametrize('inner', [certificate(), HostnameMismatch(SECRET),
    ssl.SSLError(1, SECRET), OSError(1, SECRET), SECRET])
def test_certificate_hostname_and_unknown_errors_not_retried(inner):
    retry, diagnostic = tls_failure(wrapped(inner))
    assert not retry and SECRET not in diagnostic


@pytest.mark.parametrize('link', ['__cause__', '__context__', 'reason', 'args'])
def test_certificate_has_priority_over_transient_sibling(link):
    outer = requests.exceptions.SSLError(ssl.SSLEOFError(8, SECRET))
    if link == 'args':
        outer.args += (certificate(),)
    else:
        setattr(outer, link, certificate())
    retry, diagnostic = tls_failure(outer)
    assert not retry and 'category=certificate_verification' in diagnostic
    assert 'verify_code=62' in diagnostic and 'ssl_reason=CERTIFICATE_VERIFY_FAILED' in diagnostic
    assert SECRET not in diagnostic


def test_suppressed_context_not_used_for_retry():
    outer = requests.exceptions.SSLError(SECRET)
    outer.__context__ = ssl.SSLEOFError(8, SECRET)
    outer.__suppress_context__ = True
    assert not tls_failure(outer)[0]


def test_cyclic_and_oversized_chains_are_bounded():
    outer = requests.exceptions.SSLError(SECRET)
    outer.__cause__ = outer
    retry, diagnostic = tls_failure(outer)
    assert not retry and len(diagnostic) < 200
    inner = certificate()
    for _ in range(25):
        inner = UrllibSSLError(inner)
    outer = requests.exceptions.SSLError(ssl.SSLEOFError(8, SECRET), inner)
    retry, diagnostic = tls_failure(outer)
    assert not retry and 'incomplete_exception_chain' in diagnostic
    assert len(diagnostic) < 2000


def test_excess_arguments_fail_closed():
    outer = requests.exceptions.SSLError(ssl.SSLEOFError(8, SECRET), *([SECRET] * 9), certificate())
    assert not tls_failure(outer)[0]


def test_only_structured_known_reason_can_trigger_retry():
    inner = ssl.SSLError(1, 'UNEXPECTED_EOF_WHILE_READING ' + SECRET)
    assert not tls_failure(wrapped(inner))[0]  # Never classify by raw message.
    inner.reason = 'UNEXPECTED_EOF_WHILE_READING'
    assert tls_failure(wrapped(inner))[0]
    inner.reason = SECRET
    inner.library = SECRET
    retry, diagnostic = tls_failure(wrapped(inner))
    assert not retry and SECRET not in diagnostic and 'ssl_reason=OTHER' in diagnostic


def api():
    session, sleep = Mock(), Mock()
    client = EbaySellerClient(EbayCredentials(SECRET, SECRET, SECRET), session=session, sleep=sleep)
    return client, session, sleep


def test_oauth_eof_then_success_retries_identical_request(caplog):
    client, session, sleep = api()
    session.request.side_effect = [wrapped(ssl.SSLEOFError(8, SECRET)),
        Mock(status_code=200, json=Mock(return_value={'access_token': SECRET, 'expires_in': 7200}))]
    assert client._access_token() == SECRET
    assert session.request.call_args_list[0] == session.request.call_args_list[1]
    assert session.request.call_args.args == ('POST', TOKEN_URL)
    assert session.request.call_args.kwargs['verify'] is True
    assert session.request.call_args.kwargs['allow_redirects'] is False
    sleep.assert_called_once_with(5)
    assert 'request_attempt=1/3' in caplog.text and '接口=OAuth' in caplog.text
    assert SECRET not in caplog.text and 'private.invalid' not in caplog.text


def test_trading_request_body_unchanged_on_retry():
    client, session, sleep = api()
    ok = Mock(status_code=200)
    session.request.side_effect = [wrapped(reset()), ok]
    assert client._request('POST', TRADING_URL, data=b'<PageNumber>8</PageNumber>',
                           headers={'X-EBAY-API-IAF-TOKEN': SECRET}) is ok
    assert session.request.call_args_list[0] == session.request.call_args_list[1]
    sleep.assert_called_once_with(5)


def test_repeated_eof_exhausts_existing_three_request_budget(caplog):
    client, session, sleep = api()
    session.request.side_effect = wrapped(ssl.SSLEOFError(8, SECRET))
    with pytest.raises(EbayApiError) as error:
        client._access_token()
    assert session.request.call_count == 3
    assert [c.args[0] for c in sleep.call_args_list] == [5, 15]
    assert 'request_attempt=3/3' in str(error.value)
    assert 'SSLEOFError' in str(error.value)
    assert SECRET not in str(error.value) + caplog.text
    assert client._token == ''


def test_mixed_timeout_and_tls_share_one_budget():
    client, session, sleep = api()
    session.request.side_effect = [requests.Timeout(SECRET), wrapped(ssl.SSLEOFError(8, SECRET)),
                                   wrapped(ssl.SSLEOFError(8, SECRET))]
    with pytest.raises(EbayApiError):
        client._access_token()
    assert session.request.call_count == 3
    assert [c.args[0] for c in sleep.call_args_list] == [5, 15]


@pytest.mark.parametrize('inner', [certificate(), HostnameMismatch(SECRET), ssl.SSLError(1, SECRET)])
def test_nontransient_tls_stops_immediately_without_leaking(caplog, inner):
    client, session, sleep = api()
    session.request.side_effect = wrapped(inner)
    with pytest.raises(EbayApiError) as error:
        client._access_token()
    assert session.request.call_count == 1
    sleep.assert_not_called()
    assert 'request_attempt=1/3' in str(error.value)
    assert SECRET not in str(error.value) + caplog.text


def test_certificate_after_eof_stops_remaining_retries():
    client, session, sleep = api()
    session.request.side_effect = [wrapped(ssl.SSLEOFError(8, SECRET)), wrapped(certificate())]
    with pytest.raises(EbayApiError, match='certificate_verification'):
        client._access_token()
    assert session.request.call_count == 2
    sleep.assert_called_once_with(5)


@pytest.mark.parametrize('status', [302, 400, 401, 403, 429, 500])
def test_http_errors_remain_nonretryable(status):
    client, session, sleep = api()
    session.request.return_value = Mock(status_code=status)
    with pytest.raises(EbayApiError, match=f'HTTP {status}'):
        client._access_token()
    session.request.assert_called_once()
    sleep.assert_not_called()
