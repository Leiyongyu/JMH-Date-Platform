"""基线迁移 — 映照当前真实表结构。

revision: 001_baseline
Create Date: 2026-07-15

用途：首次使用 Alembic 时，对现有数据库执行 alembic stamp 001_baseline，
之后新增字段才通过 alembic upgrade head 执行。

此文件不包含建表 SQL（表已存在），仅用于版本标记。
实际建表 DDL 见 sql/init_database.sql。
"""
revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """基线不执行任何操作。"""
    pass


def downgrade():
    """基线不回滚。"""
    pass
