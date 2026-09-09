from backend.repositories import ebay_replenishment_sales_type_repository as repository

SALES_TYPES = {"NORMAL": "正常", "BRUSH": "刷单"}


def normalize_filter(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or value.strip() not in SALES_TYPES:
        raise ValueError("销售类型只能为正常(NORMAL)或刷单(BRUSH)")
    return value.strip()


def save_sales_type(site, sku, sales_type, operator=None):
    selected = normalize_filter(sales_type)
    if selected is None:
        raise ValueError("请选择销售类型")
    for name, value, limit in (("站点", site, 100), ("SKU", sku, 255)):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ValueError(f"{name}不能为空且不能超过{limit}个字符")
    if operator is not None and (not isinstance(operator, str) or len(operator) > 64):
        raise ValueError("操作人格式无效")
    site, sku = site.strip(), sku.strip()
    repository.save(site, sku, selected, operator or "SYSTEM")
    return {"site": site, "sku": sku, "sales_type": selected}
