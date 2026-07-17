"""
数据库与应用配置
密码通过环境变量 MYSQL_PASSWORD 注入，默认使用本地开发密码。
"""
import os

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': os.environ.get('MYSQL_PASSWORD', '1qaz!QAZ'),
    'database': 'export_tax_refund',
    'charset': 'utf8mb4',
    'autocommit': False,
}

# 报关资料Excel商品表所在库
JMH_DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': os.environ.get('MYSQL_PASSWORD', '1qaz!QAZ'),
    'database': 'jmh_data_platform',
    'charset': 'utf8mb4',
    'autocommit': False,
}

# 文件上传配置
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

# SKU 标准化规则
SKU_NORMALIZE_RULES = {
    'trim': True,
    'upper': True,
    'fullwidth_to_halfwidth': True,
    'dash_normalize': True,      # 中文横线/长横线 → 英文 "-"
    'remove_inner_spaces': True,  # 删除 PDF 排版产生的内部空格
}

# 金额校验允许的舍入误差（人民币）
AMOUNT_TOLERANCE = 0.02

# 退税率默认值（小数形式）
DEFAULT_REFUND_RATE = 0.13
