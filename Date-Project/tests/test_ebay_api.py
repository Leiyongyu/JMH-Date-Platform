from unittest.mock import Mock

import pytest
import requests

from backend.ebay_api import EbayApiError, EbayCredentials, EbaySellerClient
from backend.ebay_api.listings import parse_active_page, site_from_url
from backend.ebay_api import credentials


ITEM = '''<Item><ItemID>123</ItemID><SKU>ABC-1</SKU><Title>Example</Title>
<Quantity>44</Quantity><QuantityAvailable>16</QuantityAvailable>
<SellingStatus><CurrentPrice currencyID="GBP">14.41</CurrentPrice><QuantitySold>28</QuantitySold></SellingStatus>
<ListingDetails><ViewItemURL>https://www.ebay.co.uk/itm/123</ViewItemURL></ListingDetails></Item>'''


def xml(items=ITEM, ack='Success', errors='', total=1, pages=1):
    return (f'<GetMyeBaySellingResponse xmlns="urn:ebay:apis:eBLBaseComponents"><Ack>{ack}</Ack>{errors}'
            f'<ActiveList><PaginationResult><TotalNumberOfPages>{pages}</TotalNumberOfPages>'
            f'<TotalNumberOfEntries>{total}</TotalNumberOfEntries></PaginationResult>'
            f'<ItemArray>{items}</ItemArray></ActiveList></GetMyeBaySellingResponse>').encode()


def response(*, payload=None, content=b'', status=200):
    return Mock(status_code=status, content=content, json=Mock(return_value=payload))


def client():
    session = Mock()
    session.request.side_effect = [response(payload={'access_token': 'private-access', 'expires_in': 7200}),
        response(content=user_xml()), response(content=xml())]
    return EbaySellerClient(EbayCredentials('private-id', 'private-secret', 'private-refresh'), session=session, sleep=Mock()), session


def test_full_protocol_and_safe_amount_quantity_mapping():
    api, session = client()
    result = api.active_listings_page(expected_username='expected-shop', page_size=5)
    assert session.request.call_count == 3
    token_call, identity_call, listing_call = session.request.call_args_list
    assert token_call.kwargs['data']['grant_type'] == 'refresh_token'
    assert identity_call.kwargs['headers']['X-EBAY-API-CALL-NAME'] == 'GetUser'
    assert all('apiz.ebay.com' not in c.args[1] for c in session.request.call_args_list)
    assert listing_call.kwargs['headers']['X-EBAY-API-IAF-TOKEN'] == 'private-access'
    assert 'Authorization' not in listing_call.kwargs['headers']
    assert b'<EntriesPerPage>5</EntriesPerPage>' in listing_call.kwargs['data']
    assert b'<HideVariations>false</HideVariations>' in listing_call.kwargs['data']
    for call in session.request.call_args_list:
        assert call.kwargs['verify'] is True and call.kwargs['allow_redirects'] is False
    item = result['items'][0]
    assert item['current_price'] == {'value': '14.41', 'currency': 'GBP'}
    assert (item['quantity'], item['quantity_available'], item['quantity_sold']) == (44, 16, 28)
    assert item['watch_count'] is None and item['site'] == 'UK'
    assert 'private-' not in str(result)
    assert item['raw_xml'] and result['raw_xml']


def test_credentials_repr_hides_values():
    assert 'private-' not in repr(EbayCredentials('private-id', 'private-secret', 'private-refresh'))


def test_dpapi_child_does_not_inherit_incompatible_module_path(monkeypatch, tmp_path):
    path=tmp_path/'token.dpapi'
    # No real credential used: existence and process result are mocks.
    monkeypatch.setattr(credentials.Path, 'is_file', lambda self: True)
    monkeypatch.setenv('PSMODULEPATH','incompatible-modules')
    run=Mock(return_value=Mock(returncode=0,stdout=b'private-refresh',stderr=b''))
    monkeypatch.setattr(credentials.subprocess,'run',run)
    if credentials.os.name != 'nt':
        pytest.skip('Windows DPAPI only')
    assert credentials.read_dpapi_token(str(path))=='private-refresh'
    assert not any(key.lower()=='psmodulepath' for key in run.call_args.kwargs['env'])
    assert 'private-refresh' not in str(run.call_args)


def test_missing_store_token_fails_without_using_application_token(monkeypatch):
    monkeypatch.setattr('backend.config.load_dotenv', lambda: None)
    monkeypatch.setenv('EBAY_CLIENT_ID','test-app')
    monkeypatch.setenv('EBAY_CLIENT_SECRET','test-secret')
    monkeypatch.delenv('EBAY_REFRESH_TOKEN',raising=False)
    monkeypatch.delenv('EBAY_REFRESH_TOKEN_DPAPI_FILE',raising=False)
    with pytest.raises(EbayApiError,match='店铺'):
        EbayCredentials.from_env()


def test_mismatching_identity_stops_before_trading():
    api, session = client()
    with pytest.raises(EbayApiError, match='店铺'):
        api.active_listings_page(expected_username='another-shop')
    assert session.request.call_count == 2


def test_cached_token_reused_without_second_oauth_request():
    api, session = client()
    session.request.side_effect = [response(payload={'access_token': 'private-access', 'expires_in':7200}),
                                    response(payload={'username':'expected-shop'})]
    api.identity()
    session.request.side_effect = [response(payload={'username': 'expected-shop'})]
    api.identity()
    assert session.request.call_count == 3


def user_xml(name='expected-shop', stable='immutable-user', email='private-email@example.com', ack='Success'):
    return (f'<GetUserResponse xmlns="urn:ebay:apis:eBLBaseComponents"><Ack>{ack}</Ack>'
            f'<User><UserID>{name}</UserID><EIASToken>{stable}</EIASToken><Email>{email}</Email></User>'
            '</GetUserResponse>').encode()


def test_trading_identity_cached_across_pages_and_email_not_persisted():
    api, session = client()
    identity = api.trading_identity(expected_login='private-email@example.com')
    result = api.active_listings_page(expected_username='expected-shop')
    assert session.request.call_count == 3
    assert result['seller'] == identity and identity['userId'].startswith('trading:')
    assert len(identity['userId']) == 72
    assert 'private-email' not in str(result) and 'immutable-user' not in str(result)
    with pytest.raises(EbayApiError, match='不一致'):
        api.trading_identity(expected_login='wrong@example.com')
    assert session.request.call_count == 3


def test_oauth_refresh_revalidates_identity_before_more_items():
    api, session = client()
    api.active_listings_page(expected_username='expected-shop')
    api._expires_at = 0
    session.request.side_effect = [response(payload={'access_token':'changed-access','expires_in':7200}),
                                    response(content=user_xml(name='wrong-store'))]
    with pytest.raises(EbayApiError, match='不一致'):
        api.active_listings_page(expected_username='expected-shop')
    assert session.request.call_count == 5


@pytest.mark.parametrize('body', [b'<bad>', b'<!DOCTYPE x><x/>', user_xml(stable=''), user_xml(name=''),
                                 user_xml(ack='Warning'), user_xml(ack='Failure')])
def test_trading_identity_invalid_never_requests_listings(body):
    api, session = client()
    session.request.side_effect = [response(payload={'access_token':'private-access','expires_in':7200}),response(content=body)]
    with pytest.raises(EbayApiError): api.active_listings_page(expected_username='expected-shop')
    assert session.request.call_count == 2


@pytest.mark.parametrize('status', [301, 302, 400, 401, 429, 500])
def test_http_failure_does_not_leak_response_or_follow_redirects(status):
    api, session = client()
    session.request.side_effect = [response(status=status, content=b'private-token')]
    with pytest.raises(EbayApiError) as error:
        api.identity()
    assert str(status) in str(error.value) and 'private' not in str(error.value)
    assert session.request.call_count == 1


def test_network_error_does_not_leak_credentials():
    api, session = client()
    session.request.side_effect = requests.ConnectionError('private-secret')
    with pytest.raises(EbayApiError) as error:
        api.identity()
    assert 'private' not in str(error.value)
    assert session.request.call_count == 3
    assert [c.args[0] for c in api._sleep.call_args_list] == [5,15]


def test_transient_listing_error_retries_same_page_then_recovers():
    api, session = client()
    session.request.side_effect = [response(payload={'access_token':'private-access','expires_in':7200}),
        response(content=user_xml()), requests.ConnectionError('private-token'), response(content=xml())]
    assert api.active_listings_page(expected_username='expected-shop')['returned_count'] == 1
    assert session.request.call_args_list[2] == session.request.call_args_list[3]
    api._sleep.assert_called_once_with(5)


def test_tls_error_never_retried():
    api, session = client()
    session.request.side_effect = requests.exceptions.SSLError('private-token')
    with pytest.raises(EbayApiError, match='TLS'): api.active_listings_page(expected_username='expected-shop')
    assert session.request.call_count == 1
    api._sleep.assert_not_called()


@pytest.mark.parametrize('page,size', [(0,5),(1,200),(True,5),(1,0)])
def test_invalid_paging_fails_before_network(page,size):
    api, session = client()
    with pytest.raises(ValueError):
        api.active_listings_page(page=page,page_size=size,expected_username='expected-shop')
    session.request.assert_not_called()


@pytest.mark.parametrize('ack', ['Failure','PartialFailure','unknown'])
def test_business_failure_under_http_200_is_not_empty_success(ack):
    errors='<Errors><ErrorCode>931</ErrorCode><LongMessage>private-token</LongMessage><SeverityCode>Error</SeverityCode></Errors>'
    with pytest.raises(EbayApiError) as error:
        parse_active_page(xml(ack=ack,errors=errors),page=1,page_size=5)
    assert '931' in str(error.value) and 'private' not in str(error.value)


def test_warning_zero_inventory_and_variation_preserved():
    variation='<Variations><Variation><SKU>SUB-1</SKU><Quantity>3</Quantity><StartPrice currencyID="EUR">2.10</StartPrice></Variation></Variations>'
    item=ITEM.replace('<SKU>ABC-1</SKU>','').replace('>16<','>0<').replace('</Item>',variation+'</Item>')
    result=parse_active_page(xml(items=item,ack='Warning'),page=1,page_size=5)
    assert result['items'][0]['quantity_available']==0
    assert result['items'][0]['sku'] is None
    assert result['items'][0]['variations'][0]['sku']=='SUB-1'


@pytest.mark.parametrize('raw', [b'<bad>', b'<!DOCTYPE x><x/>', '<!DOCTYPE x><x/>'.encode('utf-16'), b'<html/>',xml(items=ITEM+ITEM,total=2),xml(items='',total=2)])
def test_invalid_xml_duplicate_item_and_unexpected_empty_page_fail(raw):
    with pytest.raises(EbayApiError):
        parse_active_page(raw,page=1,page_size=5)


@pytest.mark.parametrize('url,site', [('https://www.ebay.com.au/itm/1','AU'),('https://www.ebay.fr/itm/1','FR'),
    ('https://ebay.com.evil.test/','' ),('https://evil.test/ebay.co.uk',''),('','')])
def test_site_from_hostname_not_currency_or_substring(url,site):
    assert site_from_url(url)==(site or None)
