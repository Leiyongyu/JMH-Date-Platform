"""清空测试数据，恢复空库状态。对比验证完后执行。"""
import sys, os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, '.')
from infrastructure.database import get_conn

conn = get_conn()
c = conn.cursor()
c.execute("SET FOREIGN_KEY_CHECKS = 0")
for t in ['export_detail', 'purchase_inventory', 'customs_declaration_excel_item', 'import_batch']:
    c.execute(f'DELETE FROM {t}')
    print(f'  {t}: {c.rowcount} rows deleted')
c.execute("SET FOREIGN_KEY_CHECKS = 1")
conn.commit()
c.close(); conn.close()
print("Done — 出口/进货/报关资料/批次已清空，外汇保留。")
