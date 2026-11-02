"""定时任务数据质量门禁。

每次任务成功执行后，用本次的抽取/写入/跳过行数与该任务最近几次成功运行比较：

- ``skip_ratio``     跳过（无效/重复）行占比过高，通常是上游字段变更或解析规则失效；
- ``empty_extract``  历史有数据、本次一行都没抽到，通常是接口鉴权/筛选条件出错；
- ``volume_drop``    抽取量明显低于近期中位数，常见于分页中断、时间窗口算错；
- ``volume_spike``   抽取量远高于近期中位数，常见于重复拉取或窗口放大（只告警）。

检查结果写入 ``scheduler_task_quality_check``。``DATA_QUALITY_MODE=warn``（默认）
只记录与告警日志；``block`` 时阻断级问题会让任务以 QUALITY 阶段失败，Java 侧随之
触发 Quartz 失败告警邮件。建议观察一段时间、按任务调好阈值后再切到 block。
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from statistics import median


logger = logging.getLogger(__name__)

HISTORY_SIZE = 5
# 行数太少时比例没有统计意义，不做比例类判断。
MIN_ROWS_FOR_RATIO = 100

DEFAULT_THRESHOLDS = {
    "max_skip_ratio": 0.05,
    "min_volume_ratio": 0.5,
    "max_volume_ratio": 3.0,
}

# 业务上抽取量天然波动大或允许为空的任务，在这里单独放宽。
TASK_THRESHOLDS: dict[str, dict[str, float]] = {
    # 飞书不良交易按周视图增量同步，周与周之间数量差异大。
    "feishu_bad_transaction_sync": {"min_volume_ratio": 0.1, "max_volume_ratio": 10.0},
    # Token 健康检查不产生业务数据。
    "ebay_token_health_check": {"skip": 1},
}


@dataclass(frozen=True)
class QualityIssue:
    rule: str
    severity: str  # block / warn
    message: str
    actual: float
    expected: float


class DataQualityError(RuntimeError):
    """阻断模式下质量检查不通过。带 stage/metrics，供调度器还原失败运行记录。"""

    stage = "QUALITY"

    def __init__(self, task_code: str, issues: list[QualityIssue], metrics: dict):
        self.issues = issues
        self.metrics = metrics
        super().__init__(
            f"{task_code} 数据质量检查未通过：" + "；".join(i.message for i in issues)
        )


def mode() -> str:
    value = os.getenv("DATA_QUALITY_MODE", "warn").strip().lower()
    return value if value in {"warn", "block", "off"} else "warn"


def thresholds(task_code: str) -> dict[str, float]:
    return {**DEFAULT_THRESHOLDS, **TASK_THRESHOLDS.get(task_code, {})}


def evaluate(task_code: str, result: dict, history: list[dict]) -> list[QualityIssue]:
    """纯函数：根据本次结果和最近成功运行（新到旧）给出问题列表。"""
    limits = thresholds(task_code)
    if limits.get("skip"):
        return []
    extract = int(result.get("extract_rows") or 0)
    skipped = int(result.get("skipped_rows") or 0)
    issues: list[QualityIssue] = []

    if extract >= MIN_ROWS_FOR_RATIO:
        ratio = skipped / extract
        if ratio > limits["max_skip_ratio"]:
            issues.append(QualityIssue(
                "skip_ratio", "block",
                f"跳过行占比 {ratio:.1%} 超过上限 {limits['max_skip_ratio']:.0%}"
                f"（跳过 {skipped} / 抽取 {extract}）",
                round(ratio, 4), limits["max_skip_ratio"],
            ))

    previous = [int(row.get("extract_rows") or 0) for row in history[:HISTORY_SIZE]]
    if not previous:
        return issues
    baseline = median(previous)
    if extract == 0 and baseline > 0:
        issues.append(QualityIssue(
            "empty_extract", "block",
            f"本次抽取 0 行，近 {len(previous)} 次成功运行中位数为 {baseline:g} 行",
            0, baseline,
        ))
    elif baseline >= MIN_ROWS_FOR_RATIO:
        ratio = extract / baseline
        if ratio < limits["min_volume_ratio"]:
            issues.append(QualityIssue(
                "volume_drop", "block",
                f"抽取 {extract} 行，仅为近期中位数 {baseline:g} 行的 {ratio:.0%}",
                round(ratio, 4), limits["min_volume_ratio"],
            ))
        elif ratio > limits["max_volume_ratio"]:
            issues.append(QualityIssue(
                "volume_spike", "warn",
                f"抽取 {extract} 行，是近期中位数 {baseline:g} 行的 {ratio:.1f} 倍",
                round(ratio, 4), limits["max_volume_ratio"],
            ))
    return issues


def check(task_code: str, run_id: str, result: dict, repo) -> list[QualityIssue]:
    """执行检查并落库；阻断模式下有阻断级问题时抛 DataQualityError。

    检查本身（读历史/写结果）出错只记日志，不能让一次本已成功的同步变成失败。
    """
    current_mode = mode()
    if current_mode == "off":
        return []
    try:
        history = repo.recent_completed_runs(task_code, HISTORY_SIZE)
    except Exception:
        logger.warning("数据质量检查读取历史失败 task=%s", task_code, exc_info=True)
        history = []
    issues = evaluate(task_code, result, history)
    try:
        repo.insert_quality_check(
            run_id, task_code,
            "failed" if any(i.severity == "block" for i in issues)
            else "warning" if issues else "passed",
            json.dumps([asdict(i) for i in issues], ensure_ascii=False),
        )
    except Exception:
        logger.warning("数据质量检查结果写入失败 task=%s run=%s", task_code, run_id, exc_info=True)
    for issue in issues:
        logger.warning("数据质量 %s task=%s run=%s: %s",
                       issue.severity, task_code, run_id, issue.message)
    blocking = [i for i in issues if i.severity == "block"]
    if blocking and current_mode == "block":
        raise DataQualityError(task_code, blocking, result)
    return issues
