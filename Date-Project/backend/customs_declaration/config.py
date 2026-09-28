"""报关单子应用配置，复用 Date-Project 的环境变量与数据库账号。"""

from pathlib import Path

from backend.config import settings


MODULE_ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = MODULE_ROOT / "assets" / "customs-declaration-template.xlsx"
PRODUCTS_DATABASE = settings.shop_source_database.strip() or "jmh_data_platform"

# 汇率/价格计算参数（保留旧项目业务值）。
VAT_RATE = 0.13
MARKUP_RATE = 0.15
USD_EXCHANGE_RATE = 0.14

COMPANY_INFO = {
    "name_cn": "成都巨马供应链管理有限公司",
    "name_en": "CHENGDU JUMACH SUPPLY CHAIN MANAGEMENT CO.,LTD",
    "address": (
        "1st Floor, Building 12, No. 3 Tianhe Road, "
        "Chengdu High-tech Zone, Sichuan, China"
    ),
    "tel": "(0086)19282017790",
    "buyer_name": "Hong Kong Cammy Yeson Limited",
    "buyer_address": (
        "C/O 1175 Florence Columbus Road UNITB（A12-A35）"
        "Bordentown New Jersey 08505"
    ),
    "credit_code": "91510106MACMNJMB6A",
}
