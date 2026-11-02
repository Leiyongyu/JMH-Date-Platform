"""只读业务查询工具。

每个工具直接调用对应页面使用的服务函数，保证助手给出的数字与页面一致；
所需权限与页面接口的 @PreAuthorize 相同，补货类再套用 Java 下发的负责人数据范围。
交给模型的列在这里显式列出，避免把无关字段（如采购单价）发往模型。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from backend.agent.context import SCOPE_EBAY, AgentContext
from backend.agent.tools.base import Tool, ToolResult, money

MONTH = r"^20\d{2}-(0[1-9]|1[0-2])$"
UNASSIGNED = "未分配"


# ---------------------------------------------------------------- 可查询月份

class MonthsArgs(BaseModel):
    pass


def list_report_months(context: AgentContext, _args: MonthsArgs) -> ToolResult:
    summary: dict[str, object] = {}
    if context.access.has("finance:performanceRanking:list"):
        from backend.services.performance_service import performance_months
        summary["绩效排名月份"] = [
            {"月份": row["stat_month"], "综合已就绪": row.get("combined_ready"), "部分数据": row.get("partial")}
            for row in performance_months(24)
        ]
    if context.access.has("finance:salesDashboard:list"):
        from backend.services.sales_dashboard_service import options
        summary["销售看板"] = {
            platform: {"月份": value["months"][-24:], "组别": value["groups"]}
            for platform, value in options().items()
        }
    if context.access.has("finance:monthlyInventoryReport:list"):
        from backend.services.inventory_report_etl_service import list_months
        summary["月度库存月份"] = [row.get("stat_month") for row in list_months(24)]
    if not summary:
        summary["提示"] = "当前账号没有任何报表页面权限"
    return ToolResult(title="可查询月份", summary=summary, source="各报表已保存的数据")


# ---------------------------------------------------------------- 绩效排名

class PerformanceArgs(BaseModel):
    stat_month: str | None = Field(None, pattern=MONTH, description="统计月份 YYYY-MM；不填为最新月份")
    platform: Literal["combined", "amazon", "ebay"] = Field("combined", description="combined=综合，amazon，ebay")
    principal_name: str | None = Field(None, max_length=50, description="只看某个负责人；「未分配」表示未匹配到负责人的部分")
    order_by: Literal["gross_profit", "net_sales_amount"] = Field("gross_profit", description="排序指标")
    top: int = Field(50, ge=1, le=200, description="返回前N名")


def performance_ranking(context: AgentContext, args: PerformanceArgs) -> ToolResult:
    from backend.services.performance_service import list_performance_rankings
    # 负责人通常只有十几到几十名：取全量计算合计与未分配，再截取前 N 名给模型。
    data = list_performance_rankings(
        platform=args.platform, stat_month=args.stat_month, principal_name=args.principal_name,
        order_by=args.order_by, order="desc", page=1, page_size=1000,
    )
    all_rows = [
        {"principal": item["principalNames"], "gross_profit": money(item["grossProfit"]),
         "net_sales": money(item["netSalesAmount"])}
        for item in data["items"]
    ]
    rows = all_rows[:args.top]
    gross = sum((Decimal(str(item["grossProfit"])) for item in data["items"]), Decimal(0))
    net = sum((Decimal(str(item["netSalesAmount"])) for item in data["items"]), Decimal(0))
    unassigned = next((row for row in all_rows if row["principal"] == UNASSIGNED), None)
    notes = []
    if data.get("partial"):
        notes.append("该月份排名为部分数据（某个平台尚未导入或刷新），汇总可能偏低")
    if len(all_rows) > len(rows):
        notes.append(f"共{len(all_rows)}名负责人，明细只返回前{len(rows)}名；合计为全部负责人")
    return ToolResult(
        title=f"{data['stat_month']} 绩效排名（{ {'combined': '综合', 'amazon': 'Amazon', 'ebay': 'eBay'}[args.platform] }）",
        summary={
            "统计月份": data["stat_month"], "币种": "CNY", "负责人数": len(all_rows),
            "合计毛利润": money(gross), "合计净销售额": money(net),
            "未分配毛利润": unassigned["gross_profit"] if unassigned else 0,
        },
        columns=[("principal", "负责人"), ("gross_profit", "毛利润"), ("net_sales", "净销售额")],
        rows=rows, source="绩效排名页（dws_*_performance_ranking）", period=data["stat_month"] or "", notes=notes,
    )


# ---------------------------------------------------------------- 负责人规则

class OwnerRuleArgs(BaseModel):
    stat_month: str = Field(..., pattern=MONTH, description="规则月份 YYYY-MM")
    platform: Literal["amazon", "ebay"] = "amazon"


def owner_rule_summary(context: AgentContext, args: OwnerRuleArgs) -> ToolResult:
    from backend.services.performance_service import owner_rule_summary as summary_service
    data = summary_service(args.platform, args.stat_month)
    rows = [
        {"group": item.get("group_code") or "-", "rule_type": item.get("rule_type"),
         "rule_count": item.get("rule_count"), "updated": str(item.get("last_updated_at") or "")}
        for item in data.get("items") or []
    ]
    notes = [] if rows else [f"{args.stat_month} 没有导入{args.platform}负责人规则，该月全部业绩会计入「未分配」"]
    return ToolResult(
        title=f"{args.stat_month} {args.platform} 负责人规则", summary={"规则组数": len(rows)},
        columns=[("group", "组别"), ("rule_type", "规则类型"), ("rule_count", "规则数"), ("updated", "最后导入")],
        rows=rows, source="负责人映射表导入结果（dwd_performance_owner_rule）", period=args.stat_month, notes=notes,
    )


# ---------------------------------------------------------------- 销售看板

class SalesDashboardArgs(BaseModel):
    platform: Literal["ebay", "amz"] = Field(..., description="ebay 或 amz")
    start_month: str = Field(..., pattern=MONTH)
    end_month: str = Field(..., pattern=MONTH)
    groups: list[str] = Field(default_factory=list, max_length=30,
                              description="组别筛选，如 EU、US1；不填为全部组别")


def sales_dashboard_report(context: AgentContext, args: SalesDashboardArgs) -> ToolResult:
    from backend.services.sales_dashboard_service import report
    data = report(args.platform, args.start_month, args.end_month, args.groups)
    metric_keys = [key for key in ("net_sales", "gross_profit", "platform_income", "refund_amount")
                   if key in data["metrics"]]
    rows = []
    for month_index, month in enumerate(data["months"]):
        groups = {series["name"] for key in metric_keys for series in data["metrics"][key]["series"]}
        for group in sorted(groups):
            row = {"month": month, "group": group}
            for key in metric_keys:
                series = next((s for s in data["metrics"][key]["series"] if s["name"] == group), None)
                row[key] = money(series["values"][month_index]) if series else None
            rows.append(row)
    summary = {"币种": data.get("currency", "CNY"), "月份": data["months"]}
    notes = []
    for key in ("net_sales", "gross_profit", "platform_income", "refund_amount", "gross_margin", "refund_rate"):
        metric = data["metrics"].get(key)
        if not metric:
            continue
        value = metric.get("summary", {}).get("value")
        summary[metric["label"] + "合计"] = (
            round(float(value), 4) if key in ("gross_margin", "refund_rate") and value is not None else money(value)
        )
        missing = metric.get("summary", {}).get("missing_months") or []
        if missing:
            notes.append(f"{metric['label']}缺少月份：{'、'.join(missing)}，合计不含这些月份")
    labels = {"net_sales": "净销售额", "gross_profit": "毛利润", "platform_income": "平台收入", "refund_amount": "退款金额"}
    return ToolResult(
        title=f"销售看板 {args.platform.upper()} {args.start_month}~{args.end_month}",
        summary=summary,
        columns=[("month", "月份"), ("group", "组别")] + [(key, labels[key]) for key in metric_keys],
        rows=rows, source="销售看板（财务月度数据）", period=f"{args.start_month}~{args.end_month}",
        notes=notes + ["毛利率=毛利润/平台收入；退款率=退款金额/销售总额，均按汇总后的分子分母计算"],
    )


# ---------------------------------------------------------------- 月度库存

class InventoryArgs(BaseModel):
    stat_month: str | None = Field(None, pattern=MONTH, description="统计月份；不填为最新月份")
    dimension: Literal["GROUP", "STORE", "OWNER"] = Field("GROUP", description="GROUP=组别，STORE=店铺，OWNER=负责人")


INVENTORY_COLUMNS = [
    ("name", "名称"), ("total_goods_value", "库存总货值"), ("local_end_inventory_total_cost", "本地库存成本"),
    ("overseas_end_inventory_total_cost", "海外仓库存成本"), ("fba_end_inventory_total_cost", "FBA库存成本"),
    ("monthly_sales_qty", "月销量"), ("actual_achievement_amount", "实际达成金额"),
    ("target_achievement_rate", "目标达成率"), ("inventory_age_180_plus_cost", "库龄180天以上成本"),
    ("inventory_health_rate", "库存健康率"),
]


def monthly_inventory_summary(context: AgentContext, args: InventoryArgs) -> ToolResult:
    from backend.services import inventory_report_etl_service as inventory
    if args.dimension == "GROUP":
        data = inventory.get_department_summary(args.stat_month)
        source_rows = [item for item in data.get("items") or [] if not item.get("is_total")]
        name_key = "department_name"
    else:
        data = inventory.get_dimension_summary(args.dimension, args.stat_month)
        source_rows = data.get("items") or []
        name_key = "dimension_value"
    rows = []
    for item in source_rows:
        row = {"name": item.get(name_key)}
        for key, _label in INVENTORY_COLUMNS[1:]:
            value = item.get(key)
            row[key] = round(float(value), 4) if key.endswith("_rate") and value not in (None, "") else money(value)
        if row.get("total_goods_value") is None:
            parts = [row.get(k) for k in ("local_end_inventory_total_cost", "overseas_end_inventory_total_cost",
                                          "fba_end_inventory_total_cost")]
            row["total_goods_value"] = round(sum(p for p in parts if p is not None), 2) if any(
                p is not None for p in parts) else None
        rows.append(row)
    rows.sort(key=lambda r: r.get("total_goods_value") or 0, reverse=True)
    return ToolResult(
        title=f"{data.get('stat_month')} 月度库存（{ {'GROUP': '组别', 'STORE': '店铺', 'OWNER': '负责人'}[args.dimension] }）",
        summary={"统计月份": data.get("stat_month"), "报表月份": data.get("report_month"),
                 "美元汇率": money(data.get("usd_rate"), 6), "行数": len(rows), "币种": "CNY"},
        columns=INVENTORY_COLUMNS, rows=rows, source="月度库存数据表（已保存快照）",
        period=str(data.get("stat_month") or ""),
        notes=["库存成本为期末成本；月销量与达成金额使用报表月份口径"],
    )


# ---------------------------------------------------------------- eBay 补货

class ReplenishmentArgs(BaseModel):
    site: str | None = Field(None, max_length=20, description="站点中文名，如 德国、美国、英国")
    sku: str | None = Field(None, max_length=80, description="SKU 关键词")
    product_level: str | None = Field(None, max_length=10, description="商品等级，如 A、B、C")
    principal_name: str | None = Field(None, max_length=50, description="负责人")
    sort_field: Literal["suggested_replenishment_quantity", "sales_qty_30d", "gross_profit_amount"] = Field(
        "suggested_replenishment_quantity", description="排序字段")
    top: int = Field(50, ge=1, le=200)


REPLENISHMENT_COLUMNS = [
    ("sku", "SKU"), ("site", "站点"), ("product_name", "品名"), ("principal_name", "负责人"),
    ("product_level", "等级"), ("sales_qty_30d", "近30天销量"), ("forecast_sales_quantity", "预估销量"),
    ("overseas_sellable_quantity", "海外仓可售"), ("overseas_in_transit_quantity", "海外仓在途"),
    ("suggested_replenishment_quantity", "建议补货量"), ("profit_rate", "利润率"), ("return_rate", "退货率"),
]


def ebay_replenishment(context: AgentContext, args: ReplenishmentArgs) -> ToolResult:
    from backend.services.ebay_replenishment_v2_service import list_replenishment
    allowed = context.access.scope(SCOPE_EBAY)
    if allowed == []:
        return ToolResult(title="eBay补货", notes=["当前账号在eBay补货模块没有任何数据范围"],
                          source="eBay补货2.0")
    data = list_replenishment(
        site=args.site, sku=args.sku, product_level=args.product_level, principal_name=args.principal_name,
        page=1, page_size=args.top, sort_field=args.sort_field, sort_order="desc",
        use_read_model=True, allowed_principals=allowed,
    )
    rows = [{key: item.get(key) for key, _label in REPLENISHMENT_COLUMNS} for item in data.get("items") or []]
    for row in rows:
        for key in ("profit_rate", "return_rate"):
            if row.get(key) not in (None, ""):
                row[key] = round(float(row[key]), 4)
    total = (data.get("pagination") or {}).get("total", len(rows))
    notes = [] if allowed is None else ["已按当前账号的负责人数据范围过滤"]
    if total > len(rows):
        notes.append(f"符合条件共{total}行，此处只返回排序前{len(rows)}行")
    return ToolResult(
        title="eBay补货建议", summary={"符合条件SKU数": total, "参考日期": data.get("reference_date"),
                                   "负责人规则月份": data.get("owner_rule_month")},
        columns=REPLENISHMENT_COLUMNS, rows=rows, source="eBay补货2.0（读模型快照）",
        period=str(data.get("reference_date") or ""), notes=notes,
    )


BUSINESS_TOOLS = [
    Tool("list_report_months", "列出当前账号可查询的报表及已有数据的月份、组别。不确定月份或组别时先调用。",
         MonthsArgs, list_report_months, title="查询可用月份"),
    Tool("performance_ranking", "查询绩效排名：按负责人汇总的毛利润、净销售额（人民币），可选综合/Amazon/eBay。",
         PerformanceArgs, performance_ranking, permission="finance:performanceRanking:list", title="查询绩效排名"),
    Tool("owner_rule_summary", "查询某月负责人映射规则的导入情况（各组别规则数），用于解释「未分配」。",
         OwnerRuleArgs, owner_rule_summary, permission="finance:performanceRanking:list", title="查询负责人规则"),
    Tool("sales_dashboard_report", "查询销售看板：按月份和组别的净销售额、毛利润、平台收入、退款金额及毛利率、退款率。",
         SalesDashboardArgs, sales_dashboard_report, permission="finance:salesDashboard:list", title="查询销售看板"),
    Tool("monthly_inventory_summary", "查询月度库存数据表：按组别/店铺/负责人汇总的库存货值、销量、达成率、库龄、健康率。",
         InventoryArgs, monthly_inventory_summary, permission="finance:monthlyInventoryReport:list",
         title="查询月度库存"),
    Tool("ebay_replenishment", "查询eBay补货建议：SKU的近30天销量、预估销量、海外仓库存与在途、建议补货量，按数据范围过滤。",
         ReplenishmentArgs, ebay_replenishment, permission="operations:ebayReplenishmentV2:list",
         title="查询eBay补货"),
]
