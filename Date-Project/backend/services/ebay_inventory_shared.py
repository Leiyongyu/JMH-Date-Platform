"""SKU分析与补货2.0共用的实时库存聚合；完整SKU，不受订单日期限制。"""
# 与原 eBay 补货计算链路 application.yml 中 lingxing.inventory-wids 保持一致。
# 匹配库存时仅对站点标签和完整 SKU 做等值匹配，不再截取 SKU 后缀。
_INVENTORY_SITE_BY_WID = {
    18674: "德国",  # 成都 eBay-DE 中转仓
    18675: "英国",  # 成都 eBay-UK 中转仓
    18676: "美国",  # 成都 eBay-US 中转仓
    18699: "德国",  # 谷仓德国仓
    18700: "美国",  # 谷仓美国新泽西仓
    18701: "美国",  # 谷仓美国加州仓
    18702: "英国",  # 谷仓英国仓
}
_CHENGDU_WIDS = (18674, 18675, 18676)
_OVERSEAS_WIDS = (18699, 18700, 18701, 18702)
_INVENTORY_WIDS_SQL = ",".join(str(wid) for wid in _INVENTORY_SITE_BY_WID)
_CHENGDU_WIDS_SQL = ",".join(str(wid) for wid in _CHENGDU_WIDS)
_OVERSEAS_WIDS_SQL = ",".join(str(wid) for wid in _OVERSEAS_WIDS)
_INVENTORY_SITE_CASE_SQL = " ".join(
    f"WHEN {wid} THEN '{site}'" for wid, site in _INVENTORY_SITE_BY_WID.items()
)

FIELDS = ("chengdu_in_transit_quantity", "chengdu_sellable_quantity",
          "overseas_in_transit_quantity", "overseas_sellable_quantity")


def enrich_sku_items(cursor, items):
    """只补当前页，先聚合库存再按站点+完整SKU关联，不参与订单SUM。"""
    if not items:
        return
    requested = " UNION ALL ".join("SELECT %s row_no, %s site, %s sku" for _ in items)
    params = []
    for index, item in enumerate(items):
        params.extend((index, item["site_name"], item["inventory_sku"]))
        item.update({key: "0" for key in FIELDS})
    columns = ",".join(f"COALESCE(i.{key},0) {key}" for key in FIELDS)
    cursor.execute(f"""
        WITH {inventory_ctes()}, requested AS ({requested})
        SELECT r.row_no,{columns} FROM requested r
        LEFT JOIN inventory_summary i
          ON CONVERT(i.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT(r.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
         AND CONVERT(i.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT(r.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
    """, params)
    for row in cursor.fetchall():
        items[int(row["row_no"])].update({key: str(row[key]) for key in FIELDS})


def inventory_ctes():
    return f"""
        inventory_source AS (
            SELECT CASE source.wid {_INVENTORY_SITE_CASE_SQL} END site,
                   TRIM(source.sku) sku,
                   CASE WHEN source.wid IN ({_CHENGDU_WIDS_SQL})
                        THEN COALESCE(source.quantity_receive,0) ELSE 0 END
                       chengdu_in_transit_quantity,
                   CASE WHEN source.wid IN ({_CHENGDU_WIDS_SQL})
                        THEN COALESCE(source.product_valid_num,0) ELSE 0 END
                       chengdu_sellable_quantity,
                   CASE WHEN source.wid IN ({_OVERSEAS_WIDS_SQL})
                        THEN COALESCE(source.product_onway,0) ELSE 0 END
                       overseas_in_transit_quantity,
                   CASE WHEN source.wid IN ({_OVERSEAS_WIDS_SQL})
                        THEN COALESCE(source.product_valid_num,0) ELSE 0 END
                       overseas_sellable_quantity
            FROM jmh_data_platform.warehouse_inventory_detail source
            WHERE source.wid IN ({_INVENTORY_WIDS_SQL})
              AND source.sku IS NOT NULL AND TRIM(source.sku)<>''
        ),
        inventory_summary AS (
            SELECT site,sku,
                   SUM(chengdu_in_transit_quantity) chengdu_in_transit_quantity,
                   SUM(chengdu_sellable_quantity) chengdu_sellable_quantity,
                   SUM(overseas_in_transit_quantity) overseas_in_transit_quantity,
                   SUM(overseas_sellable_quantity) overseas_sellable_quantity
            FROM inventory_source
            GROUP BY site,sku
        )
    """
