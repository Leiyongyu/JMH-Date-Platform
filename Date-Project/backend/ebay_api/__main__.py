"""只取指定一页并打印安全的商品样本，不自动翻页、不写数据库或凭证。"""
import argparse
import json

from . import EbayApiError, EbayCredentials, EbaySellerClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-seller', required=True)
    parser.add_argument('--token-file', help='可选：现有Windows DPAPI加密Refresh Token文件')
    parser.add_argument('--page-size', type=int, default=5, choices=range(1, 101))
    args = parser.parse_args()
    client = None
    try:
        client = EbaySellerClient(EbayCredentials.from_env(token_file=args.token_file))
        result = client.active_listings_page(page=1, page_size=args.page_size, expected_username=args.expected_seller)
        preview = {k: v for k, v in result.items() if k not in ('raw_xml', 'items')}
        preview['items'] = [{k: item[k] for k in ('item_id', 'sku', 'site', 'current_price',
                                                  'quantity', 'quantity_available', 'quantity_sold')}
                            for item in result['items'][:5]]
        print(json.dumps(preview, ensure_ascii=True, indent=2))
    except EbayApiError as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=True))
        return 1
    finally:
        if client:
            client.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
