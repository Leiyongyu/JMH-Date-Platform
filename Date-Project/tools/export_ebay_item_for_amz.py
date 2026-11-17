"""按 eBay 参考链接（或同 SKU 的同款刊登）导出 Amazon 上架所需的商品资料。

只读：调用 Trading API `GetItem` 取标题、属性、图片、描述与适配车型，SKU 兜底来源是
`ods_ebay_store_listing_latest` 快照（只 SELECT，不写库）。产出按 SKU 分目录保存原始
XML、规范化 JSON、描述 HTML/纯文本、适配车型 CSV 与 1600px 原图，并汇总一本总表。

运行（Date-Project 目录）：

    .venv\\Scripts\\python.exe -m tools.export_ebay_item_for_amz ^
        --workbook "C:\\Users\\a\\Desktop\\eBay月销大于15-2.xlsx" ^
        --out outputs\\amz-listing-source

凭证与 backend/ebay_api 一致：优先 --token-file，其次 .env 的
EBAY_REFRESH_TOKEN_DPAPI_FILE / EBAY_REFRESH_TOKEN，最后按店铺凭证工作簿逐个尝试。
GetItem 不要求商品归属授权店铺，任一可用店铺令牌即可读取全部参考链接。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from html import unescape
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

from backend.config import PROJECT_ROOT, load_dotenv
from backend.ebay_api.accounts import configured_accounts, credentials_for
from backend.ebay_api.credentials import EbayApiError, EbayCredentials
from backend.ebay_api.client import EbaySellerClient

NS = '{urn:ebay:apis:eBLBaseComponents}'
TRADING_URL = 'https://api.ebay.com/ws/api.dll'
MAX_RESPONSE_BYTES = 20_000_000
# Trading SITEID：站点影响标题/属性/描述的语种，必须按商品所在站点请求。
SITE_IDS = {'US': '0', 'UK': '3', 'GB': '3', 'DE': '77', 'FR': '71', 'IT': '101', 'ES': '186',
            'NL': '146', 'PL': '212', 'AU': '15', 'CA': '2', 'AT': '16', 'CH': '193', 'IE': '205'}
HOST_SITES = {'ebay.com': 'US', 'ebay.co.uk': 'UK', 'ebay.de': 'DE', 'ebay.fr': 'FR', 'ebay.it': 'IT',
              'ebay.es': 'ES', 'ebay.nl': 'NL', 'ebay.pl': 'PL', 'ebay.com.au': 'AU', 'ebay.ca': 'CA',
              'ebay.at': 'AT', 'ebay.ch': 'CH', 'ebay.ie': 'IE'}
SPECIFIC_ALIASES = {
    'brand': ('Brand', 'Hersteller', 'Marke', 'Marque', 'Marca'),
    'mpn': ('MPN', 'Manufacturer Part Number', 'Herstellernummer', 'Référence fabricant',
            'Numero di riferimento OE/OEM'),
    'ean': ('EAN', 'GTIN', 'UPC'),
    'oe': ('OE/OEM Part Number', 'OE/OEM Referenznummer(n)', 'OE/OEM Reference Number(s)',
           'Reference OE/OEM', 'OE/OEM Referenznummer'),
}


def _text(node, path: str) -> str:
    if node is None:
        return ''
    found = node.findtext(NS + path.replace('/', '/' + NS))
    return (found or '').strip()


def parse_item_id(link: str) -> str:
    """从参考链接取刊登号；兼容 /itm/<标题>/<id> 与链接中标题被写坏的情况。"""
    if not link:
        return ''
    found = re.findall(r'(\d{9,15})', str(link))
    return found[-1] if found else ''


def site_from_link(link: str) -> str:
    match = re.search(r'https?://(?:www\.)?([a-z0-9.\-]+)', str(link or ''), re.I)
    if not match:
        return ''
    return HOST_SITES.get(match.group(1).lower(), '')


def html_to_text(html: str) -> str:
    body = re.sub(r'(?s)<!--.*?-->', ' ', html or '')
    body = re.sub(r'(?is)<(script|style|head)\b.*?</\1>', ' ', body)
    body = re.sub(r'(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|table)>', '\n', body)
    body = re.sub(r'(?i)</t[dh]>', '\t', body)
    body = unescape(re.sub(r'(?s)<[^>]+>', '', body))
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in body.splitlines()]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(line for line in lines if line)).strip()


def core_description(html: str) -> str:
    """刊登模板里 schema.org 的 description 段落，就是卖家写的产品正文。"""
    match = re.search(r'(?is)<span[^>]*property="description"[^>]*>(.*?)</span>', html or '')
    return html_to_text(match.group(1)) if match else ''


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[^0-9A-Za-z._\-]+', '_', str(value or '')).strip('_')
    return cleaned[:80] or 'unknown'


class ItemReader:
    """逐个读取 GetItem；令牌按店铺凭证顺序回退，日志不含令牌或响应正文。"""

    def __init__(self, *, token_file: str | None, pause: float):
        self._pause = pause
        self._session = requests.Session()
        self._clients = self._build_clients(token_file)
        self._client = None
        self._last_call = 0.0

    @staticmethod
    def _build_clients(token_file: str | None) -> list:
        load_dotenv()
        candidates = []
        try:
            candidates.append(EbayCredentials.from_env(token_file=token_file))
        except EbayApiError:
            if token_file:
                raise
        if not token_file:
            try:
                candidates.extend(credentials_for(account) for account in configured_accounts())
            except EbayApiError:
                pass
        if not candidates:
            raise EbayApiError('没有可用的 eBay 店铺凭证，无法读取商品资料')
        return [EbaySellerClient(credential) for credential in candidates]

    def close(self):
        for client in self._clients:
            client.close()
        self._session.close()

    def _token(self) -> str:
        if self._client is not None:
            return self._client._access_token()
        for index, client in enumerate(self._clients):
            try:
                token = client._access_token()
            except EbayApiError:
                print(f'  第{index + 1}个店铺凭证不可用，尝试下一个', flush=True)
                continue
            self._client = client
            return token
        raise EbayApiError('所有店铺凭证都无法换取访问令牌')

    def get_item(self, item_id: str, site: str) -> bytes:
        body = ('<?xml version="1.0" encoding="utf-8"?>'
                '<GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">'
                '<DetailLevel>ReturnAll</DetailLevel>'
                '<IncludeItemSpecifics>true</IncludeItemSpecifics>'
                '<IncludeItemCompatibilityList>true</IncludeItemCompatibilityList>'
                f'<ItemID>{item_id}</ItemID></GetItemRequest>')
        wait = self._pause - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        headers = {'X-EBAY-API-CALL-NAME': 'GetItem', 'X-EBAY-API-IAF-TOKEN': self._token(),
                   'X-EBAY-API-COMPATIBILITY-LEVEL': '1193',
                   'X-EBAY-API-SITEID': SITE_IDS.get((site or '').upper(), '0'),
                   'Content-Type': 'text/xml; charset=utf-8'}
        try:
            response = self._session.post(TRADING_URL, data=body.encode('utf-8'), headers=headers,
                                          timeout=(10, 120), allow_redirects=False, verify=True)
        except requests.RequestException:
            raise EbayApiError('GetItem 请求失败；不输出敏感异常正文') from None
        finally:
            self._last_call = time.monotonic()
        if response.status_code != 200:
            raise EbayApiError(f'GetItem 请求失败 HTTP {response.status_code}')
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise EbayApiError('GetItem 响应超出安全上限')
        return response.content


def parse_item(raw: bytes) -> dict:
    try:
        decoded = raw.decode('utf-8-sig')
        if '<!DOCTYPE' in decoded.upper() or '<!ENTITY' in decoded.upper():
            raise ValueError()
        root = ET.fromstring(decoded)
    except (UnicodeError, ValueError, ET.ParseError):
        raise EbayApiError('GetItem 响应 XML 异常') from None
    ack = _text(root, 'Ack')
    if root.tag != NS + 'GetItemResponse' or ack not in ('Success', 'Warning'):
        codes = sorted({_text(e, 'ErrorCode') for e in root.findall(NS + 'Errors')} - {''})
        raise EbayApiError(f'GetItem 未成功；Ack={ack or "缺失"} 错误码={",".join(codes) or "无"}')
    item = root.find(NS + 'Item')
    if item is None:
        raise EbayApiError('GetItem 响应缺少商品节点')

    specifics, specifics_flat = [], {}
    container = item.find(NS + 'ItemSpecifics')
    for pair in (container.findall(NS + 'NameValueList') if container is not None else []):
        name = _text(pair, 'Name')
        values = [(v.text or '').strip() for v in pair.findall(NS + 'Value')]
        values = [v for v in values if v]
        if not name or not values:
            continue
        specifics.append({'name': name, 'values': values})
        specifics_flat.setdefault(name.casefold(), ' | '.join(values))

    def alias(key: str) -> str:
        for name in SPECIFIC_ALIASES[key]:
            if name.casefold() in specifics_flat:
                return specifics_flat[name.casefold()]
        return ''

    pictures, seen = [], set()
    details = item.find(NS + 'PictureDetails')
    for node in (details.findall(NS + 'PictureURL') if details is not None else []):
        url = (node.text or '').strip()
        if url and url not in seen:
            seen.add(url)
            pictures.append(url)

    compatibility = []
    compat_list = item.find(NS + 'ItemCompatibilityList')
    for entry in (compat_list.findall(NS + 'Compatibility') if compat_list is not None else []):
        values = {}
        for pair in entry.findall(NS + 'NameValueList'):
            name = _text(pair, 'Name')
            if name:
                values[name] = ' | '.join((v.text or '').strip() for v in pair.findall(NS + 'Value')).strip()
        notes = _text(entry, 'CompatibilityNotes')
        if notes:
            values['CompatibilityNotes'] = notes
        if values:
            compatibility.append(values)

    description = _text(item, 'Description')
    selling = item.find(NS + 'SellingStatus')
    return {
        'item_id': _text(item, 'ItemID'),
        'sku': _text(item, 'SKU'),
        'title': _text(item, 'Title'),
        'subtitle': _text(item, 'Subtitle'),
        'seller': _text(item.find(NS + 'Seller'), 'UserID'),
        'site': _text(item, 'Site'),
        'country': _text(item, 'Country'),
        'currency': _text(item, 'Currency'),
        'price': _text(selling, 'CurrentPrice') or _text(item, 'StartPrice'),
        'quantity': _text(item, 'Quantity'),
        'quantity_sold': _text(selling, 'QuantitySold'),
        'condition_id': _text(item, 'ConditionID'),
        'condition': _text(item, 'ConditionDisplayName'),
        'category_id': _text(item.find(NS + 'PrimaryCategory'), 'CategoryID'),
        'category_path': _text(item.find(NS + 'PrimaryCategory'), 'CategoryName'),
        'secondary_category_id': _text(item.find(NS + 'SecondaryCategory'), 'CategoryID'),
        'view_item_url': _text(item.find(NS + 'ListingDetails'), 'ViewItemURL'),
        'brand': alias('brand'),
        'mpn': alias('mpn'),
        'ean': alias('ean'),
        'oe_numbers': alias('oe'),
        'package_length': _text(item.find(NS + 'ShippingPackageDetails'), 'PackageLength'),
        'package_width': _text(item.find(NS + 'ShippingPackageDetails'), 'PackageWidth'),
        'package_depth': _text(item.find(NS + 'ShippingPackageDetails'), 'PackageDepth'),
        'weight_major': _text(item.find(NS + 'ShippingPackageDetails'), 'WeightMajor'),
        'weight_minor': _text(item.find(NS + 'ShippingPackageDetails'), 'WeightMinor'),
        'specifics': specifics,
        'pictures': pictures,
        'compatibility': compatibility,
        'compatibility_reported_count': _text(item, 'ItemCompatibilityCount'),
        'description_html': description,
        'description_text': html_to_text(description),
        'description_core': core_description(description),
        'regulatory_json': regulatory(item),
    }


def regulatory(item) -> dict:
    """GPSR 制造商/负责人信息，Amazon 欧洲站上架需要。"""
    node = item.find(NS + 'Regulatory')
    if node is None:
        return {}

    def walk(element):
        children = list(element)
        if not children:
            return (element.text or '').strip()
        collected = {}
        for child in children:
            key = child.tag.replace(NS, '')
            value = walk(child)
            if value in ('', {}, []):
                continue
            if key in collected:
                existing = collected[key]
                collected[key] = existing + [value] if isinstance(existing, list) else [existing, value]
            else:
                collected[key] = value
        return collected

    return walk(node) or {}


def full_size_url(url: str) -> str:
    """eBay EPS 图片按变体后缀取最大尺寸；$_57 为 1600px 原图。"""
    return re.sub(r'\$_\d+\.(JPG|PNG|WEBP)', r'$_57.\1', url, flags=re.I)


def download_pictures(urls: list[str], folder: Path, session: requests.Session) -> list[dict]:
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for index, url in enumerate(urls, 1):
        candidates = [full_size_url(url)]
        if candidates[0] != url:
            candidates.append(url)
        for candidate in candidates:
            try:
                response = session.get(candidate, timeout=(10, 120))
            except requests.RequestException:
                continue
            if response.status_code != 200 or len(response.content) < 1024:
                continue
            suffix = '.png' if response.content[:4] == b'\x89PNG' else '.webp' if response.content[:4] == b'RIFF' else '.jpg'
            name = f'{index:02d}{suffix}'
            (folder / name).write_bytes(response.content)
            saved.append({'seq': index, 'source_url': url, 'downloaded_url': candidate,
                          'file': name, 'bytes': len(response.content)})
            break
        else:
            saved.append({'seq': index, 'source_url': url, 'downloaded_url': '', 'file': '', 'bytes': 0})
    return saved


def read_workbook_rows(path: Path) -> list[dict]:
    workbook = load_workbook(path, data_only=True)
    sheet = workbook.worksheets[0]
    try:
        headers = [str(cell.value or '').strip() for cell in next(sheet.iter_rows(max_row=1))]
        index = {name: position for position, name in enumerate(headers)}
        sku_at = index.get('SKU', 1)
        name_at = index.get('商品名称', 2)
        site_at = index.get('站点', 0)
        note_at = index.get('是否在做', 11)
        link_at = index.get('参考链接', 12)
        rows = []
        for row_no, cells in enumerate(sheet.iter_rows(min_row=2), 2):
            def value(position):
                return cells[position].value if position < len(cells) else None
            sku = str(value(sku_at) or '').strip()
            if not sku:
                continue
            cell = cells[link_at] if link_at < len(cells) else None
            link = ''
            if cell is not None:
                link = (cell.hyperlink.target if cell.hyperlink else '') or str(cell.value or '')
            rows.append({'row_no': row_no, 'sku': sku, 'name': str(value(name_at) or '').strip(),
                         'site': str(value(site_at) or '').strip(), 'note': str(value(note_at) or '').strip(),
                         'link': link.strip()})
        return rows
    finally:
        workbook.close()


def sibling_listings(skus: list[str], sites: list[str], per_site: int) -> dict:
    """同 SKU 的其他站点同款刊登，用于拿到英文/德文两套文案；只读月度快照。"""
    if not skus or not sites or per_site < 1:
        return {}
    import pymysql

    from backend.config import settings
    connection = pymysql.connect(host=settings.mysql_host, port=settings.mysql_port,
                                 user=settings.mysql_user, password=settings.mysql_password,
                                 database=settings.mysql_database, charset='utf8mb4',
                                 cursorclass=pymysql.cursors.DictCursor)
    try:
        with connection.cursor() as cursor:
            placeholders = ','.join(['%s'] * len(skus))
            site_holders = ','.join(['%s'] * len(sites))
            cursor.execute(
                'SELECT sku, item_id, seller_account, site, title, quantity_sold, stat_month '
                'FROM ods_ebay_store_listing_latest '
                f'WHERE sku IN ({placeholders}) AND site IN ({site_holders}) '
                'ORDER BY sku, site, CAST(COALESCE(quantity_sold, 0) AS SIGNED) DESC, item_id',
                [*skus, *(s.upper() for s in sites)])
            found = cursor.fetchall()
    finally:
        connection.close()
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in found:
        grouped.setdefault((row['sku'], row['site']), []).append(row)
    return {key: value[:per_site] for key, value in grouped.items()}


def export(args) -> int:
    workbook_path = Path(args.workbook).expanduser()
    if not workbook_path.is_file():
        print(f'找不到台账文件：{workbook_path}', file=sys.stderr)
        return 2
    out_root = Path(args.out).expanduser()
    if not out_root.is_absolute():
        out_root = PROJECT_ROOT / out_root
    out_root.mkdir(parents=True, exist_ok=True)

    rows = read_workbook_rows(workbook_path)
    linked = [row for row in rows if parse_item_id(row['link'])]
    print(f'台账共 {len(rows)} 行，其中带参考链接 {len(linked)} 行，'
          f'去重 SKU {len({row["sku"] for row in linked})} 个')

    targets, problems = [], []
    for row in linked:
        item_id = parse_item_id(row['link'])
        site = site_from_link(row['link']) or ('UK' if row['site'] == '英国' else 'DE' if row['site'] == '德国'
                                               else 'US' if row['site'] == '美国' else '')
        targets.append({'sku': row['sku'], 'name': row['name'], 'row_no': row['row_no'], 'item_id': item_id,
                        'site': site, 'source': '参考链接', 'link': row['link'], 'seller': ''})

    sites = [s.strip().upper() for s in (args.sibling_sites or '').split(',') if s.strip()]
    if sites:
        skus = sorted({row['sku'] for row in linked})
        try:
            siblings = sibling_listings(skus, sites, args.siblings_per_site)
        except Exception as error:  # 兜底来源不可用时不阻断参考链接导出
            siblings = {}
            problems.append({'sku': '', 'item_id': '', 'stage': '同SKU兜底',
                             'detail': f'读取月度快照失败：{type(error).__name__}'})
            print(f'  同SKU兜底不可用（{type(error).__name__}），只导出参考链接', flush=True)
        taken = {target['item_id'] for target in targets}
        names = {row['sku']: row['name'] for row in linked}
        for (sku, site), listings in sorted(siblings.items()):
            for listing in listings:
                if listing['item_id'] in taken:
                    continue
                taken.add(listing['item_id'])
                targets.append({'sku': sku, 'name': names.get(sku, ''), 'row_no': 0,
                                'item_id': listing['item_id'], 'site': site, 'source': f'同SKU-{site}',
                                'link': '', 'seller': listing['seller_account']})
    if args.limit:
        targets = targets[:args.limit]
    print(f'待抓取刊登 {len(targets)} 条' + (f'（含同SKU同款 {len(targets) - len(linked)} 条）' if sites else ''))

    reader = ItemReader(token_file=args.token_file, pause=args.pause)
    picture_session = requests.Session()
    exported, pictures_rows, specifics_rows, compatibility_rows = [], [], [], []
    try:
        for position, target in enumerate(targets, 1):
            folder = out_root / safe_name(target['sku']) / f'{target["site"] or "NA"}-{target["item_id"]}'
            folder.mkdir(parents=True, exist_ok=True)
            raw_path = folder / 'raw.xml'
            label = f'[{position}/{len(targets)}] {target["sku"]} {target["item_id"]} {target["source"]}'
            try:
                if raw_path.is_file() and not args.refresh:
                    raw = raw_path.read_bytes()
                    print(f'{label} 复用已保存响应', flush=True)
                else:
                    raw = reader.get_item(target['item_id'], target['site'])
                    raw_path.write_bytes(raw)
                item = parse_item(raw)
            except EbayApiError as error:
                print(f'{label} 失败：{error}', flush=True)
                problems.append({'sku': target['sku'], 'item_id': target['item_id'],
                                 'stage': 'GetItem', 'detail': str(error)})
                continue

            (folder / 'description.html').write_text(item['description_html'], encoding='utf-8')
            (folder / 'description.txt').write_text(item['description_text'], encoding='utf-8')
            if item['description_core']:
                (folder / 'description_core.txt').write_text(item['description_core'], encoding='utf-8')
            if item['compatibility']:
                columns, seen = [], set()
                for entry in item['compatibility']:
                    for key in entry:
                        if key not in seen:
                            seen.add(key)
                            columns.append(key)
                with (folder / 'compatibility.csv').open('w', encoding='utf-8-sig', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(item['compatibility'])

            # 同 SKU 同款刊登的图片通常与参考链接重复，默认只下参考链接的图。
            want_images = not args.no_images and (target['source'] == '参考链接' or args.sibling_images)
            saved_pictures = (download_pictures(item['pictures'], folder / 'images', picture_session)
                              if want_images else [])
            record = {**item, **target, 'listing_sku': item['sku'], 'ebay_site': item['site'],
                      'seller': item['seller'] or target['seller'], 'folder': str(folder),
                      'sku_matches_workbook': (item['sku'] or '').casefold() == target['sku'].casefold(),
                      'pictures_saved': saved_pictures}
            (folder / 'item.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            exported.append(record)
            if not record['sku_matches_workbook']:
                problems.append({'sku': target['sku'], 'item_id': target['item_id'], 'stage': 'SKU核对',
                                 'detail': f'刊登SKU={item["sku"] or "未返回"}，与台账不一致'})
            for entry in item['specifics']:
                specifics_rows.append({'sku': target['sku'], 'item_id': item['item_id'],
                                       'name': entry['name'], 'value': ' | '.join(entry['values'])})
            for picture in saved_pictures:
                pictures_rows.append({'sku': target['sku'], 'item_id': item['item_id'], **picture})
                if not picture['file']:
                    problems.append({'sku': target['sku'], 'item_id': item['item_id'], 'stage': '图片下载',
                                     'detail': f'第{picture["seq"]}张未下载成功'})
            for entry in item['compatibility']:
                compatibility_rows.append({'sku': target['sku'], 'item_id': item['item_id'], **entry})
            print(f'{label} 属性{len(item["specifics"])} 图片{len(saved_pictures)}/{len(item["pictures"])} '
                  f'车型{len(item["compatibility"])}（eBay计数{item["compatibility_reported_count"] or "-"}）',
                  flush=True)
    finally:
        reader.close()
        picture_session.close()

    summary_path = out_root / '商品资料总表.xlsx'
    write_summary(summary_path, exported, specifics_rows, pictures_rows, compatibility_rows, problems)
    print(f'\n导出完成：成功 {len(exported)} / {len(targets)} 条，异常 {len(problems)} 项')
    print(f'总表：{summary_path}')
    print(f'明细目录：{out_root}')
    return 0 if exported else 1


def write_summary(path: Path, exported, specifics_rows, pictures_rows, compatibility_rows, problems):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = '商品'
    headers = ['SKU', '台账品名', '来源', '台账行', 'ItemID', '店铺', '站点', '标题', '价格', '币种',
               '刊登数量', '已售', '成色', '类目ID', '类目路径', '品牌', '制造商编号', 'EAN',
               'OE/OEM号', '属性数', '图片数', '已存图片', '车型数(接口)', '车型数(eBay计数)',
               'SKU与台账一致', '商品链接', '本地目录']
    sheet.append(headers)
    for item in exported:
        sheet.append([item['sku'], item['name'], item['source'],
                      item['row_no'] or '', item['item_id'], item['seller'],
                      item['ebay_site'] or item['site'], item['title'], item['price'], item['currency'],
                      item['quantity'],
                      item['quantity_sold'], item['condition'], item['category_id'], item['category_path'],
                      item['brand'], item['mpn'], item['ean'], item['oe_numbers'], len(item['specifics']),
                      len(item['pictures']), sum(1 for p in item['pictures_saved'] if p['file']),
                      len(item['compatibility']), item['compatibility_reported_count'],
                      '是' if item['sku_matches_workbook'] else '否',
                      item['view_item_url'] or item['link'], item['folder']])

    def add_sheet(title, columns, rows):
        target = workbook.create_sheet(title)
        target.append(columns)
        for row in rows:
            target.append([row.get(column, '') for column in columns])
        return target

    add_sheet('商品属性', ['sku', 'item_id', 'name', 'value'], specifics_rows)
    add_sheet('图片', ['sku', 'item_id', 'seq', 'file', 'bytes', 'downloaded_url', 'source_url'], pictures_rows)
    compat_columns, seen = ['sku', 'item_id'], {'sku', 'item_id'}
    for row in compatibility_rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                compat_columns.append(key)
    add_sheet('适配车型', compat_columns, compatibility_rows)
    add_sheet('异常', ['sku', 'item_id', 'stage', 'detail'], problems)
    for worksheet in workbook.worksheets:
        for position, column in enumerate(next(worksheet.iter_rows(max_row=1)), 1):
            width = min(60, max(10, len(str(column.value or '')) * 2 + 4))
            worksheet.column_dimensions[get_column_letter(position)].width = width
        worksheet.freeze_panes = 'A2'
    workbook.save(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='导出 eBay 参考链接商品资料用于 Amazon 上架（只读）')
    parser.add_argument('--workbook', required=True, help='含参考链接的台账 xlsx 路径')
    parser.add_argument('--out', default='outputs/amz-listing-source', help='导出目录')
    parser.add_argument('--token-file', default=None, help='指定 DPAPI 令牌文件；默认按 .env 与店铺工作簿回退')
    parser.add_argument('--sibling-sites', default='US,UK,DE',
                        help='额外抓取同 SKU 同款刊登的站点（逗号分隔，留空只抓参考链接）')
    parser.add_argument('--siblings-per-site', type=int, default=1, help='每个站点抓取的同 SKU 刊登条数')
    parser.add_argument('--pause', type=float, default=0.8, help='两次 GetItem 之间的最小间隔秒数')
    parser.add_argument('--no-images', action='store_true', help='只导出文本资料，不下载图片')
    parser.add_argument('--sibling-images', action='store_true', help='同 SKU 同款刊登也下载图片')
    parser.add_argument('--refresh', action='store_true', help='忽略已保存的 raw.xml，重新请求')
    parser.add_argument('--limit', type=int, default=0, help='只处理前 N 条刊登，用于小样本试跑')
    args = parser.parse_args(argv)
    try:
        return export(args)
    except EbayApiError as error:
        print(f'导出中止：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
