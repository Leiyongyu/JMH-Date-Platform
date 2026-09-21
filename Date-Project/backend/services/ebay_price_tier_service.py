"""兼容原eBay报表路由，读取独立美元五档统计。"""
from backend.services import listing_price_tier_service as service


def read_report():
    return service.read_report('ebay')


def refresh_report():
    return service.refresh_report('ebay')
