"""独立的 eBay 卖家接口模块，不写业务库、不触发同步或修改店铺。"""
from .client import EbaySellerClient
from .credentials import EbayCredentials, EbayApiError

__all__ = ['EbaySellerClient', 'EbayCredentials', 'EbayApiError']
