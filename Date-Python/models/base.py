"""数据库连接管理 — 现在统一走 infrastructure.database 连接池"""
from infrastructure.database import get_conn as _get_conn, get_jmh_conn as _get_jmh_conn


def get_conn():
    return _get_conn()


def get_jmh_conn():
    return _get_jmh_conn()


def init_database():
    """创建数据库（如不存在）"""
    config_no_db = {k: v for k, v in DB_CONFIG.items() if k != 'database'}
    conn = mysql.connector.connect(**config_no_db)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE DATABASE IF NOT EXISTS `{}` "
        "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci".format(DB_CONFIG['database'])
    )
    cursor.close()
    conn.close()


def init_tables():
    """从 SQL 文件初始化表"""
    sql_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sql', 'init_database.sql')
    conn = get_conn()
    cursor = conn.cursor()
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    statements = []
    current = []
    for line in sql_content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('--') or stripped == '':
            continue
        current.append(line)
        if stripped.endswith(';'):
            statements.append('\n'.join(current))
            current = []
    for stmt in statements:
        try:
            cursor.execute(stmt)
        except Exception as e:
            pass  # 表已存在等情况忽略
    conn.commit()
    cursor.close()
    conn.close()
