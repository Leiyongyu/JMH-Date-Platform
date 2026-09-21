"""Trading ActiveList解析：保留原始字段；金额用Decimal，缺值不是0。"""
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from .credentials import EbayApiError

NS = '{urn:ebay:apis:eBLBaseComponents}'


class MissingActiveList(EbayApiError):
    """A valid Trading envelope with no requested list; never an empty inventory."""
    def __init__(self, *, ack, codes, page, page_size, response_bytes):
        self.retryable = ack == 'Success'
        safe_ack = ack if ack in ('Success', 'Warning') else 'OTHER'
        # Only bounded numeric codes; never include LongMessage or response XML.
        safe_codes = [c for c in codes if c and c.isascii() and c.isdecimal() and len(c) <= 12][:10]
        super().__init__(
            f'Trading响应缺少ActiveList，不当作空数据；ack={safe_ack} '
            f'warning_codes={",".join(safe_codes) or "-"} page={page} '
            f'page_size={page_size} response_bytes={response_bytes}')


SITES = {'ebay.co.uk': 'UK', 'ebay.de': 'DE', 'ebay.fr': 'FR', 'ebay.it': 'IT',
         'ebay.es': 'ES', 'ebay.com': 'US', 'ebay.com.au': 'AU', 'ebay.ca': 'CA',
         'ebay.at': 'AT', 'ebay.ch': 'CH', 'ebay.nl': 'NL', 'ebay.be': 'BE',
         'ebay.pl': 'PL', 'ebay.ie': 'IE', 'ebay.com.hk': 'HK', 'ebay.com.sg': 'SG'}


def text(node, path):
    return node.findtext('/'.join(NS + p for p in path.split('/')), '').strip() or None


def number(node, path, *, integer=False, required=False):
    raw = text(node, path)
    if raw is None:
        if required:
            raise EbayApiError('Trading响应缺少必需数量字段')
        return None
    try:
        value = Decimal(raw)
        if not value.is_finite() or value < 0 or (integer and value != value.to_integral_value()):
            raise ValueError()
        return int(value) if integer else str(value)
    except (ValueError, InvalidOperation):
        raise EbayApiError('Trading响应数量或金额格式异常') from None


def money(node, path):
    element = node.find('/'.join(NS + p for p in path.split('/')))
    return {'value': number(node, path), 'currency': element.get('currencyID') if element is not None else None}


def site_from_url(url):
    try:
        host = (urlsplit(url or '').hostname or '').lower()
    except ValueError:
        return None
    return next((site for domain, site in SITES.items() if host == domain or host.endswith('.' + domain)), None)


def parse_active_page(raw: bytes, *, page: int, page_size: int) -> dict:
    if len(raw) > 10 * 1024 * 1024:
        raise EbayApiError('Trading单页响应超过10MB限制')
    try:
        decoded = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise EbayApiError('Trading响应不是预期的UTF-8 XML') from None
    if '<!DOCTYPE' in decoded.upper() or '<!ENTITY' in decoded.upper():
        raise EbayApiError('Trading XML包含不允许的DTD或实体定义')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise EbayApiError('Trading返回无效XML，不输出原始响应正文') from None
    if root.tag != NS + 'GetMyeBaySellingResponse':
        raise EbayApiError('Trading响应根节点不符合GetMyeBaySelling')
    ack = text(root, 'Ack')
    errors = root.findall(NS + 'Errors')
    codes = [text(e, 'ErrorCode') for e in errors]
    safe_codes = [c for c in codes if c and c.isascii() and c.isdecimal()]
    if ack not in ('Success', 'Warning') or any(text(e, 'SeverityCode') == 'Error' for e in errors):
        raise EbayApiError('GetMyeBaySelling业务失败；错误码=' + ','.join(safe_codes))
    active = root.find(NS + 'ActiveList')
    if active is None:
        raise MissingActiveList(ack=ack, codes=safe_codes, page=page, page_size=page_size,
                                response_bytes=len(raw))
    total = number(active, 'PaginationResult/TotalNumberOfEntries', integer=True, required=True)
    pages = number(active, 'PaginationResult/TotalNumberOfPages', integer=True, required=True)
    items = []
    seen = set()
    for item in active.findall(NS + 'ItemArray/' + NS + 'Item'):
        item_id = text(item, 'ItemID')
        if not item_id or item_id in seen:
            raise EbayApiError('Trading页内ItemID缺失或重复，拒绝掩盖分页异常')
        seen.add(item_id)
        url = text(item, 'ListingDetails/ViewItemURL')
        variations = []
        for variation in item.findall(NS + 'Variations/' + NS + 'Variation'):
            variations.append({'sku': text(variation, 'SKU'), 'price': money(variation, 'StartPrice'),
                               'quantity': number(variation, 'Quantity', integer=True),
                               'quantity_sold': number(variation, 'SellingStatus/QuantitySold', integer=True),
                               'raw_xml': ET.tostring(variation, encoding='unicode')})
        items.append({'item_id': item_id, 'sku': text(item, 'SKU'), 'title': text(item, 'Title'),
                      'site': site_from_url(url), 'current_price': money(item, 'SellingStatus/CurrentPrice'),
                      'buy_it_now_price': money(item, 'BuyItNowPrice'),
                      'quantity': number(item, 'Quantity', integer=True),
                      'quantity_available': number(item, 'QuantityAvailable', integer=True),
                      'quantity_sold': number(item, 'SellingStatus/QuantitySold', integer=True),
                      'watch_count': number(item, 'WatchCount', integer=True),
                      'listing_type': text(item, 'ListingType'), 'listing_duration': text(item, 'ListingDuration'),
                      'time_left': text(item, 'TimeLeft'), 'start_time': text(item, 'ListingDetails/StartTime'),
                      'view_item_url': url, 'image_url': text(item, 'PictureDetails/GalleryURL'),
                      'variations': variations, 'raw_xml': ET.tostring(item, encoding='unicode')})
    if len(items) > page_size or len(items) > total or (total > 0 and pages == 0):
        raise EbayApiError('Trading返回分页数量异常')
    if total > 0 and page <= pages and not items:
        raise EbayApiError('Trading返回意外空页')
    item_array = active.find(NS + 'ItemArray')
    if item_array is not None:
        active.remove(item_array)
    return {'ack': ack, 'warning_codes': safe_codes, 'timestamp': text(root, 'Timestamp'),
            'response_envelope_xml': ET.tostring(root, encoding='unicode'),
            'page': page, 'page_size': page_size, 'total_entries': total, 'total_pages': pages,
            'returned_count': len(items), 'has_more': page < pages, 'items': items,
            'raw_xml': decoded}
