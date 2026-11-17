"""Read-only local smoke check; no HTTP calls, no table initialization, no saves."""
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import json
import subprocess
import sys
import types
from pathlib import Path
import pymysql
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import settings
from backend.services import ebay_replenishment_v2_service as v2
from backend.services import ebay_sku_analysis_service as sku
from backend.repositories import ebay_replenishment_v2_repository as repo

@contextmanager
def readonly_connection():
    if settings.mysql_host not in {"127.0.0.1","localhost","::1"}:
        raise RuntimeError("Only local inspection allowed")
    connection=pymysql.connect(host=settings.mysql_host,port=settings.mysql_port,
        user=settings.mysql_user,password=settings.mysql_password,database=settings.mysql_database,
        charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,autocommit=False,read_timeout=60)
    with connection.cursor() as cursor:
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
    try: yield connection
    finally:
        connection.rollback()
        connection.close()

def main():
    sku._ensure_tables=lambda:None
    sku.db_connection=readonly_connection
    repo.db_connection=readonly_connection
    v2.db_connection=readonly_connection
    root=Path(__file__).resolve().parents[2]
    # Load the unchanged HEAD implementation in memory to compare all original fields.
    source=subprocess.check_output(["git","show","HEAD:Date-Project/backend/services/ebay_replenishment_v2_service.py"],
                                   cwd=root).decode("utf-8")
    baseline=types.ModuleType("inventory_upgrade_baseline")
    exec(compile(source,"HEAD:ebay_replenishment_v2_service.py","exec"),baseline.__dict__)
    baseline.db_connection=readonly_connection
    old=baseline.list_replenishment(page=1,page_size=200)
    current=v2.list_replenishment(page=1,page_size=200)
    assert old["pagination"]==current["pagination"]
    old_map={(r["site"],r["sku"]):r for r in old["items"]}
    differences=[]
    for row in current["items"]:
        key=(row["site"],row["sku"])
        for field,value in old_map[key].items():
            if row[field]!=value: differences.append([key,field])
    assert not differences, differences[:10]
    result=sku.list_summary(None,None,None,None,None,None,1,200)
    source_sku=subprocess.check_output(["git","show","HEAD:Date-Project/backend/services/ebay_sku_analysis_service.py"],
                                       cwd=root).decode("utf-8")
    baseline_sku=types.ModuleType("sku_upgrade_baseline")
    exec(compile(source_sku,"HEAD:ebay_sku_analysis_service.py","exec"),baseline_sku.__dict__)
    baseline_sku.db_connection=readonly_connection
    baseline_sku._ensure_tables=lambda:None
    old_sku=baseline_sku.list_summary(None,None,None,None,None,None,1,200)
    assert result["summary"]==old_sku["summary"] and result["chart"]==old_sku["chart"]
    old_sku_map={(row["site_name"],row["inventory_sku"]):row for row in old_sku["items"]}
    for row in result["items"]:
        assert all(row[field]==value for field,value in old_sku_map[(row["site_name"],row["inventory_sku"])].items())
    keys=[dict(site_name=row["site"],inventory_sku=row["sku"]) for row in current["items"]]
    from backend.services.ebay_inventory_shared import enrich_sku_items,FIELDS
    with readonly_connection() as connection, connection.cursor() as cursor:
        enrich_sku_items(cursor,keys)
    for row,stock in zip(current["items"],keys):
        assert all(Decimal(row[f])==Decimal(stock[f]) for f in FIELDS)
    assert len(result["items"])>0
    assert all(all(field in row for field in FIELDS) for row in result["items"])
    # The same full SKU across two date ranges must receive identical current inventory.
    chosen=result["items"][0]
    with readonly_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT DATE(MAX(payment_time)) last_date FROM dwd_ebay_sku_analysis_order WHERE site_name=%s AND inventory_sku=%s",
                       (chosen["site_name"],chosen["inventory_sku"]))
        day=cursor.fetchone()["last_date"].isoformat()
    other=sku.list_summary(day,day,
                          chosen["inventory_sku"],chosen["site_name"],None,None,1,200)
    exact=[r for r in other["items"] if r["inventory_sku"]==chosen["inventory_sku"]]
    assert exact and all(Decimal(exact[0][f])==Decimal(chosen[f]) for f in FIELDS)
    output=dict(baseline_rows=len(old_map),existing_field_differences=len(differences),
                inventory_rows_compared=len(keys),sku_page_rows=len(result["items"]),
                sku_existing_fields_unchanged=True,sku_chart_and_summary_unchanged=True,
                date_filter_comparison="passed" if exact else "no_orders_in_second_range",
                second_safety_with_values=sum(r["safety_stock_quantity_2"] is not None for r in current["items"]),
                total=current["pagination"]["total"],read_only=True)
    print(json.dumps(output,ensure_ascii=False))
if __name__=="__main__": main()
