"""eBay库存明细产品等级：按历史最大月销与利润率计算，不再依赖上传的等级表。

阈值表逐档抄自业务方Excel公式（产品等级列），列号对应：
    K = 历史最大月销，J = 利润率

    =IF(K<=4, IF(J>=0.15,"D","E"),
     IF(K<=9, IF(J>=0.15,"C",IF(J>=0.1,"D",IF(J>=0.05,"E","E"))),
     IF(K<=14,IF(J>=0.3,"A",IF(J>=0.2,"A",IF(J>=0.18,"B",IF(J>=0.15,"C",
              IF(J>=0.1,"D",IF(J>=0.05,"D","E")))))),
     IF(K<=19,IF(J>=0.3,"S",IF(J>=0.2,"A",IF(J>=0.18,"B",IF(J>=0.15,"C",
              IF(J>=0.1,"C",IF(J>=0.05,"D","E")))))),
     IF(K<=29,IF(J>=0.3,"S",IF(J>=0.2,"A",IF(J>=0.18,"B",IF(J>=0.15,"C",
              IF(J>=0.1,"C",IF(J>=0.05,"D","E")))))),
              IF(J>=0.2,"S",IF(J>=0.18,"B",IF(J>=0.15,"C",
              IF(J>=0.1,"C",IF(J>=0.05,"D","E")))))))))

公式里有几档相邻结果相同（例如K<=14时0.3与0.2都是A、0.1与0.05都是D），
这里保留原样不合并，方便逐行与Excel核对，也便于业务方单独调某一档。
"""
from __future__ import annotations

from decimal import Decimal

# (历史最大月销上界, ((利润率下界, 等级), ...), 兜底等级)
# 上界 None 表示最后一档，无上界。档位按上界升序，命中第一个即停。
GRADE_BANDS: tuple[tuple[int | None, tuple[tuple[str, str], ...], str], ...] = (
    (4, (("0.15", "D"),), "E"),
    (9, (("0.15", "C"), ("0.1", "D"), ("0.05", "E")), "E"),
    (14, (("0.3", "A"), ("0.2", "A"), ("0.18", "B"), ("0.15", "C"),
          ("0.1", "D"), ("0.05", "D")), "E"),
    (19, (("0.3", "S"), ("0.2", "A"), ("0.18", "B"), ("0.15", "C"),
          ("0.1", "C"), ("0.05", "D")), "E"),
    (29, (("0.3", "S"), ("0.2", "A"), ("0.18", "B"), ("0.15", "C"),
          ("0.1", "C"), ("0.05", "D")), "E"),
    (None, (("0.2", "S"), ("0.18", "B"), ("0.15", "C"),
            ("0.1", "C"), ("0.05", "D")), "E"),
)

GRADES: tuple[str, ...] = ("S", "A", "B", "C", "D", "E")


def calculate_grade(max_monthly_sales, profit_rate) -> str | None:
    """返回S/A/B/C/D/E；利润率缺失时返回None（页面显示--）。

    利润率为None代表三个月销售额为0，除不出比率。Excel里这种行是#DIV/0!，
    不是"利润率低"，因此不落到E，而是不给等级，避免把无数据当成差评级。
    没有历史销量按0处理：0是真实的"从没卖过"，不是缺失。
    """
    if profit_rate is None:
        return None
    rate = profit_rate if isinstance(profit_rate, Decimal) else Decimal(str(profit_rate))
    if not rate.is_finite():
        return None
    sales = Decimal(0) if max_monthly_sales is None else Decimal(str(max_monthly_sales))
    if not sales.is_finite():
        return None
    for upper, tiers, fallback in GRADE_BANDS:
        if upper is not None and sales > upper:
            continue
        for threshold, grade in tiers:
            if rate >= Decimal(threshold):
                return grade
        return fallback
    return None
