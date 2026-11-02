"""按问题难度选择思考模式与模型（AI_AGENT_THINKING_MODE=auto 时生效）。

只对「明显不需要查数据」的短句关闭思考：寒暄、致谢、确认类短句。判断不准时一律按复杂问题处理，
宁可多花一点时间，也不让需要分析的问题少了思考。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend.config import settings

DATA_HINT = re.compile(
    r"多少|几|哪些|哪个|排名|前\d|top|对比|比较|环比|同比|趋势|销量|销售|毛利|利润|收入|退款|库存|补货|"
    r"负责人|未分配|月份|\d{1,2}\s*月|本月|上月|上周|今天|昨天|店铺|站点|sku|订单|看板|报表|统计|"
    r"怎么算|口径|为什么|原因|分析|导出|明细",
    re.IGNORECASE,
)
SIMPLE_MAX_CHARS = 20


@dataclass(frozen=True)
class Route:
    simple: bool
    thinking: bool
    model: str | None


def choose(question: str) -> Route:
    mode = settings.ai_agent_thinking_mode
    if not settings.ai_agent_thinking_enabled or mode == "off":
        return Route(simple=False, thinking=False, model=None)
    if mode == "on":
        return Route(simple=False, thinking=True, model=None)
    text = (question or "").strip()
    simple = len(text) <= SIMPLE_MAX_CHARS and not DATA_HINT.search(text)
    if simple:
        return Route(simple=True, thinking=False, model=settings.ai_agent_simple_model or None)
    return Route(simple=False, thinking=True, model=None)
