"""eBay SKU 月度不良交易量与成交均价：由飞书不良交易刊登表算出，按月×店铺×SKU。

单价 = 该月最大登记日期那一批里，按店铺+SKU 汇总的 总交易额 / 总交易量。
源表金额本来就是美元，不换汇。

读取方只剩产品结构的「不良交易率」那张图，它用的是这里的 total_qty 与
defect_qty。价格档已经不由这张表定了——源表只收录**有不良交易的**刊登，
SKU 远不全（实测 2026-09 只有 372 个 SKU，而同月在售刊登有 2023 个），
拿它当价格结构的主表，看到的是问题刊登的价格分布而不是商品的价格分布。
价格档现在统一来自在售刊登，见 ebay_listing_price_repository。
unit_price / tier_no 两列仍然算着，作为这张表自己的口径留档。
"""
from __future__ import annotations

import re
from datetime import datetime

from backend.database import db_connection
from backend.services import listing_price_tier_service as engine

TABLE = "dws_ebay_sku_unit_price"
SOURCE_TABLE = "ods_feishu_bad_transaction_listing"
_BATCH_SIZE = 500

# 一个统计月份里源表有4~5批（每周三一批）。三条规则，缺一不可：
#
# 1. SKU全集取整月的并集，不是只取最后一批。实测2026-09四批合起来有1062个
#    店铺SKU，只看最后一批只有435个，会丢掉627个。
#
# 2. 交易量与不良量在同一个店铺SKU上跨批次取 MAX，绝不相加。源表给的是评估
#    窗口内的累计数，同一个SKU每批都会重报一次：BMW-30034-0046 三批分别是
#    6、7、7，相加得20，实际只有7。
#
# 3. 单价取该店铺SKU**自己**最大登记日期那一批的 金额÷数量。不能拿整月最大量
#    去配另一批的金额——那是两批的数字，比值没有意义。
#    （数字并非单调递增：BMW-30213-0071 的不良量走过 1→2→1，是滚动窗口；
#     实测372个多批次店铺SKU里有80个的最大量不在最后一批。）
#
# 同一批次内同一店铺SKU的多个刊登（不同物品编号）仍然相加——那是不同刊登的
# 成交，本来就该合并。所以是"批次内求和、批次间取最大"。
# 店铺名清洗：去掉换行、首尾空白，以及开头残留的逗号（源表里有 ', stellar-hub'
# 这种值）。ODS 保持原样，只在这里归一。
SHOP_EXPR = "TRIM(BOTH ',' FROM TRIM(BOTH FROM REPLACE(REPLACE(b.shop, CHAR(10), ' '), CHAR(13), ' ')))"
# 没有真实登记日期的行不参与统计：它们归不到任何批次，混进来会多出一个假月份。
# 业务方把原先空着的那批填成了占位日期 1999-01-01（实测419行），所以不能只判
# NULL，还要挡住明显早于业务起始的占位值。源表最早的真实批次是 2026-04-01。
MIN_REG_DATE = "2020-01-01"


def _clean_name(name):
    """与 SHOP_EXPR 等价的 Python 版，用来在内存里推导改名映射。"""
    text = str(name or "")
    for char in (chr(10), chr(13)):
        text = text.replace(char, " ")
    return text.strip().strip(",").strip()


def _match_key(name):
    """比对用的键：只留字母数字并统一小写，抹平大小写与 -、_、空格的差异。"""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def shop_aliases(cursor):
    """从数据里自动推导「旧店铺名 -> 新店铺名」。

    业务方在 2026-09-23 那批把店铺统一加了公司前缀（Aplus-Shop ->
    帝蓝泰江-ebay-Aplus-Shop），历史批次仍是短名。不归一的话同一个店铺会被
    当成两家，SKU 也被拆成两份（实测9月店铺数从37虚增到73）。

    规则：清洗后按「只留字母数字、统一小写」的键比对，若 A 的键是且仅是一个
    更长的 B 的键的后缀，则 A 视作 B。匹配到多个就不合并并记进 warnings——
    宁可少合也不能错合。等业务方把历史批次改成新名，短名消失，映射自然变空。

    忽略大小写与分隔符是必要的，改名时这两样都不一致：
      autoteile-hub   -> 帝蓝泰江-eBay-Autoteile Hub   （连字符 vs 空格，388行）
      treasures-zone  -> 帝蓝泰江-eBay-Treasures Zone  （同上，378行）
      Ace-autoteile   -> ebay-湘彦-ACE_Autoteile       （连字符 vs 下划线，且大小写不一，219行）
    只按原样后缀匹配，这985行会被当成另外三家店。实测放宽后 20 对、0 歧义。
    """
    cursor.execute(f"SELECT DISTINCT {SHOP_EXPR} AS shop FROM {SOURCE_TABLE} b "
                   f"WHERE b.shop IS NOT NULL "
                   f"AND b.reg_date IS NOT NULL AND b.reg_date >= '{MIN_REG_DATE}'")
    names = sorted({_clean_name(r["shop"]) for r in cursor.fetchall()} - {""})
    keys = {name: _match_key(name) for name in names}
    aliases, warnings = {}, []
    for short in names:
        key = keys[short]
        longer = [n for n in names if n != short and keys[n].endswith(key) and len(keys[n]) > len(key)]
        if len(longer) == 1:
            aliases[short] = longer[0]
        elif longer:
            warnings.append(f"店铺「{short}」同时是 {len(longer)} 个店铺名的后缀，未合并：{'、'.join(longer)}")
    # 合并成多级链条时一路指到最终名，避免 A->B 而 B->C 时 A 停在 B。
    for short in list(aliases):
        seen = {short}
        while aliases.get(aliases[short]) and aliases[short] not in seen:
            seen.add(aliases[short])
            aliases[short] = aliases[aliases[short]]
    return aliases, warnings


def _aggregate_sql(aliases):
    """拼出聚合SQL；aliases 把旧店铺名映射到新名，空映射时退化成纯清洗。

    别名用 CASE 而不是建映射表：这份映射是从数据里推出来的，业务方把历史批次
    改成新名之后它自然变空，不需要谁去维护一张表。
    """
    shop = SHOP_EXPR
    if aliases:
        whens = " ".join(["WHEN %s THEN %s"] * len(aliases))
        shop = f"CASE {shop} {whens} ELSE {shop} END"
    params = [value for pair in aliases.items() for value in pair]
    return AGGREGATE_TEMPLATE.format(shop_expr=shop, min_reg_date=MIN_REG_DATE), params


AGGREGATE_TEMPLATE = f"""
    WITH per_batch AS (
        -- 店铺名先清洗（换行、首尾空白、开头逗号），再按 shop_aliases 归一到
        -- 改名后的新名。不做这两步，同一个店铺会被当成两家、SKU也被拆成两份。
        -- 用 CHAR(10)/CHAR(13) 而不是转义字面量：这段SQL是Python的f-string，
        -- 写反斜杠n会在拼串时变成真的换行，把上面的注释截断。
        SELECT DATE_FORMAT(b.reg_date,'%%Y-%%m') AS stat_month,
               {{shop_expr}} AS shop,
               TRIM(b.sku) AS sku, b.reg_date,
               COUNT(*) AS listing_count,
               SUM(CAST(NULLIF(TRIM(b.total_amount),'') AS DECIMAL(20,6))) AS total_amount,
               SUM(CAST(NULLIF(TRIM(b.total_qty),'')    AS DECIMAL(20,6))) AS total_qty,
               SUM(CAST(NULLIF(TRIM(b.defect_qty),'')   AS DECIMAL(20,6))) AS defect_qty
        FROM {SOURCE_TABLE} b
        WHERE b.reg_date IS NOT NULL AND b.reg_date >= '{{min_reg_date}}'
          AND b.shop IS NOT NULL AND TRIM(b.shop) <> ''
          AND b.sku  IS NOT NULL AND TRIM(b.sku)  <> ''
        GROUP BY 1, 2, 3, b.reg_date
    ),
    ranked AS (
        SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.stat_month, p.shop, p.sku
                                       ORDER BY p.reg_date DESC) AS rn,
               MAX(p.total_qty)  OVER (PARTITION BY p.stat_month, p.shop, p.sku) AS peak_qty,
               MAX(p.defect_qty) OVER (PARTITION BY p.stat_month, p.shop, p.sku) AS peak_defect
        FROM per_batch p
    )
    SELECT stat_month, shop, sku, reg_date, listing_count,
           total_amount AS price_amount, total_qty AS price_qty,
           peak_qty  AS total_qty,
           peak_defect AS defect_qty
    FROM ranked WHERE rn = 1
"""


def aggregate(cursor, months=None):
    """按月×店铺×SKU 聚合出单价；总交易量非正的行丢弃并计数。

    months 为 None 时算全部月份（首次建表/回填）；给了就只算这些月份（每周刷新）。
    """
    aliases, alias_warnings = shop_aliases(cursor)
    sql, params = _aggregate_sql(aliases)
    if months:
        placeholders = ",".join(["%s"] * len(months))
        sql = f"{sql} AND stat_month IN ({placeholders})"
        params += list(months)
    args = tuple(params)
    cursor.execute(sql, args)
    rows, skipped = [], 0
    for row in cursor.fetchall():
        # 单价用该店铺SKU自己最大登记日期那一批的金额与数量，两者同批才可比。
        amount, qty = row["price_amount"], row["price_qty"]
        # 总交易量为0或缺失就算不出单价；丢掉并计数，不拿0或NULL冒充价格。
        if qty is None or qty <= 0 or amount is None or amount < 0:
            skipped += 1
            continue
        price = amount / qty
        rows.append({
            "stat_month": row["stat_month"], "shop": row["shop"], "sku": row["sku"],
            "reg_date": row["reg_date"], "listing_count": row["listing_count"],
            "total_amount": amount,
            # 交易量与不良量取整月最大，不是单价那一批的值：同一SKU跨批次重报，
            # 相加会翻倍，取最后一批又会漏掉峰值出现在中间批次的情况。
            "total_qty": row["total_qty"] or 0, "defect_qty": row["defect_qty"] or 0,
            "unit_price": price,
            # 档位逻辑只此一处，与页面分档共用同一套阈值。
            "tier_no": engine.tier_index(price, "USD") + 1,
        })
    return rows, skipped, alias_warnings


def refresh(months=None):
    """重算并覆盖这些月份的单价。整批一个事务，失败全回滚。

    同月重复计算直接覆盖：源表每周三更新，一个月内会被刷新4~5次。
    该月算不出来的旧行会被删掉，不留上一批的残影。
    """
    columns = ("stat_month", "shop", "sku", "reg_date", "listing_count",
               "total_amount", "total_qty", "defect_qty", "unit_price", "tier_no")
    insert_sql = (f"INSERT INTO {TABLE} (" + ",".join(f"`{c}`" for c in columns)
                  + ",computed_at) VALUES (" + ",".join(["%s"] * len(columns)) + ",%s) "
                  + "ON DUPLICATE KEY UPDATE "
                  + ",".join(f"`{c}`=VALUES(`{c}`)" for c in columns[3:])
                  + ",computed_at=VALUES(computed_at)")
    computed_at = datetime.now().replace(microsecond=0)
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                rows, skipped, alias_warnings = aggregate(cursor, months)
                alias_count = len(shop_aliases(cursor)[0])
                touched = sorted({row["stat_month"] for row in rows})
                for offset in range(0, len(rows), _BATCH_SIZE):
                    chunk = rows[offset:offset + _BATCH_SIZE]
                    cursor.executemany(insert_sql, [
                        tuple(row[c] for c in columns) + (computed_at,) for row in chunk])
                seen = {(r["stat_month"], r["shop"], r["sku"]) for r in rows}
                # months=None 是整表重算，这时"本次没算出结果"就等于"不该存在"，
                # 按整表清理。只算指定月份时仍按月清理，别动没算的月份。
                removed = (_drop_all_stale(cursor, seen) if months is None
                           else _drop_stale(cursor, touched, seen))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"months": touched, "rows": len(rows), "skipped_rows": skipped,
            "removed_rows": removed, "shop_aliases": alias_count,
            "warnings": alias_warnings}


def _drop_stale(cursor, months, seen):
    """本次算过的月份里，库里有但这次算不出来的行删掉。没算的月份一行不碰。"""
    removed = 0
    for month in months:
        cursor.execute(f"SELECT shop,sku FROM {TABLE} WHERE stat_month=%s", (month,))
        stale = [(r["shop"], r["sku"]) for r in cursor.fetchall()
                 if (month, r["shop"], r["sku"]) not in seen]
        for offset in range(0, len(stale), _BATCH_SIZE):
            chunk = stale[offset:offset + _BATCH_SIZE]
            clause = " OR ".join(["(shop=%s AND sku=%s)"] * len(chunk))
            args = [month] + [value for pair in chunk for value in pair]
            cursor.execute(f"DELETE FROM {TABLE} WHERE stat_month=%s AND ({clause})", args)
            removed += cursor.rowcount
    return removed


def latest_month(cursor):
    cursor.execute(f"SELECT MAX(stat_month) AS m FROM {TABLE}")
    row = cursor.fetchone()
    return (row or {}).get("m") or ""


def unit_prices(cursor, stat_month):
    """某个月的全部单价行，供价格分层使用。"""
    cursor.execute(
        f"SELECT stat_month,shop,sku,unit_price,total_qty,defect_qty,listing_count,reg_date "
        f"FROM {TABLE} WHERE stat_month=%s ORDER BY shop,sku", (stat_month,))
    return list(cursor.fetchall())


def months(cursor=None):
    """单价表里有哪些统计月份，新到旧。页面的月份筛选器用它。"""
    def query(cur):
        cur.execute(f"SELECT DISTINCT stat_month FROM {TABLE} ORDER BY stat_month DESC")
        return [r["stat_month"] for r in cur.fetchall()]
    if cursor is not None:
        return query(cursor)
    with db_connection() as connection, connection.cursor() as cur:
        return query(cur)


def _drop_all_stale(cursor, seen):
    """整表重算后，本次没算出来的行一律删掉。

    按月清理管不到「整个月份不再产出结果」的情况：加了登记日期下限之后
    1999-01 那个占位月份不再有行，但它上一次算出来的414行没人删，
    月份选择器里会一直挂着一个假月份。
    """
    cursor.execute(f"SELECT stat_month,shop,sku FROM {TABLE}")
    stale = [(r["stat_month"], r["shop"], r["sku"]) for r in cursor.fetchall()
             if (r["stat_month"], r["shop"], r["sku"]) not in seen]
    removed = 0
    for offset in range(0, len(stale), _BATCH_SIZE):
        chunk = stale[offset:offset + _BATCH_SIZE]
        clause = " OR ".join(["(stat_month=%s AND shop=%s AND sku=%s)"] * len(chunk))
        args = [value for triple in chunk for value in triple]
        cursor.execute(f"DELETE FROM {TABLE} WHERE {clause}", args)
        removed += cursor.rowcount
    return removed

