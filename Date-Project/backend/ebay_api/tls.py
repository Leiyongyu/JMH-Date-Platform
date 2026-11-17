"""Conservative TLS classification; never stringify request-bearing exceptions."""
from __future__ import annotations

import errno
import ssl
from collections import deque

from urllib3.util.ssl_match_hostname import CertificateError as HostnameMismatch

MAX_EXCEPTION_NODES = 16
MAX_EXCEPTION_ARGS = 8
SAFE_SSL_REASONS = {
    'CERTIFICATE_VERIFY_FAILED', 'UNEXPECTED_EOF_WHILE_READING',
    'WRONG_VERSION_NUMBER', 'TLSV1_ALERT_PROTOCOL_VERSION',
    'SSLV3_ALERT_HANDSHAKE_FAILURE', 'TLSV1_ALERT_UNKNOWN_CA',
    'TLSV1_ALERT_ACCESS_DENIED', 'SSLV3_ALERT_BAD_CERTIFICATE',
}
SAFE_SSL_LIBRARIES = {'SSL', 'X509', 'PEM', 'ASN1'}
RESET_ERRNOS = {errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE, errno.ETIMEDOUT}
RESET_WINERRORS = {10053, 10054, 10060}


def _exceptions(exc):
    # requests -> MaxRetryError.reason -> urllib3.SSLError.args -> ssl error.
    # Traverse all exception-valued links so a certificate error always wins.
    pending, seen, chain, truncated = deque([exc]), set(), [], False
    while pending:
        item = pending.popleft()
        if not isinstance(item, BaseException) or id(item) in seen:
            continue
        if len(chain) >= MAX_EXCEPTION_NODES:
            truncated = True
            break
        seen.add(id(item))
        chain.append(item)
        pending.append(item.__cause__)
        if not item.__suppress_context__:
            pending.append(item.__context__)
        pending.append(getattr(item, 'reason', None))
        args = item.args
        if len(args) > MAX_EXCEPTION_ARGS:
            truncated = True
        pending.extend(arg for arg in args[:MAX_EXCEPTION_ARGS] if isinstance(arg, BaseException))
    return chain, truncated


def tls_failure(exc):
    """Return (retryable, safe diagnostics); unknown/certificate errors fail closed."""
    chain, truncated = _exceptions(exc)
    names, fields = [], []
    for index, item in enumerate(chain):
        name = type(item).__name__ if type(item).__module__ in {
            'builtins', 'ssl', 'requests.exceptions', 'urllib3.exceptions',
            'urllib3.util.ssl_match_hostname',
        } else 'OtherException'
        names.append(name)
        for field in ('errno', 'winerror', 'verify_code'):
            value = getattr(item, field, None)
            if isinstance(value, int) and not isinstance(value, bool) and abs(value) <= 2**31:
                fields.append(f'cause{index}.{field}={int(value)}')
        if isinstance(item, ssl.SSLError):
            for field, allowed in (('library', SAFE_SSL_LIBRARIES), ('reason', SAFE_SSL_REASONS)):
                value = getattr(item, field, None)
                if isinstance(value, str):
                    fields.append(f'cause{index}.ssl_{field}={value if value in allowed else "OTHER"}')
        elif isinstance(getattr(item, 'reason', None), str):
            fields.append(f'cause{index}.reason_type=str')
    certificate = any(isinstance(item, (ssl.SSLCertVerificationError, HostnameMismatch))
                      or (isinstance(item, ssl.SSLError)
                          and getattr(item, 'reason', None) == 'CERTIFICATE_VERIFY_FAILED') for item in chain)
    unknown_ssl = any(isinstance(item, ssl.SSLError)
                      and not isinstance(item, (ssl.SSLEOFError, ssl.SSLZeroReturnError))
                      and getattr(item, 'reason', None) != 'UNEXPECTED_EOF_WHILE_READING' for item in chain)
    transient = any(isinstance(item, (ssl.SSLEOFError, ssl.SSLZeroReturnError))
                    or (isinstance(item, ssl.SSLError)
                        and getattr(item, 'reason', None) == 'UNEXPECTED_EOF_WHILE_READING')
                    or (isinstance(item, OSError) and not isinstance(item, ssl.SSLError)
                        and (item.errno in RESET_ERRNOS
                             or getattr(item, 'winerror', None) in RESET_WINERRORS)) for item in chain)
    retry = transient and not certificate and not unknown_ssl and not truncated
    category = ('certificate_verification' if certificate else 'incomplete_exception_chain' if truncated
                else 'temporary_tls_disconnect' if retry else 'unknown_or_permanent_tls')
    return retry, ' '.join([f'category={category}', 'exception_chain=' + '->'.join(names), *fields])
