"""知识类工具：指标口径说明、项目文档检索。两者都不访问业务数据。

- metric_definitions：口径来自对应服务代码，修改计算逻辑时请同步更新这里；
- search_docs：对白名单目录里的 Markdown 文档做关键词检索（中文按字二元组、英文按单词），
  按标题切段，含密码、密钥、令牌等字样的行在建索引时直接丢弃，不会进入检索结果。
"""
from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from backend.agent.context import AgentContext
from backend.agent.tools.base import Tool, ToolResult
from backend.config import PROJECT_ROOT

# ---------------------------------------------------------------- 指标口径

METRICS: list[dict[str, str]] = [
    {"name": "毛利润（绩效排名）", "page": "绩效排名",
     "definition": "Amazon 取领星 Amazon 订单利润的毛利润，eBay 取导入的 eBay SKU 利润表的毛利润，"
                   "按月份与负责人汇总，人民币。"},
    {"name": "净销售额（绩效排名）", "page": "绩效排名",
     "definition": "Amazon 取领星订单利润中的净销售额，eBay 取 SKU 利润表的净销售额，按负责人汇总，人民币。"},
    {"name": "未分配", "page": "绩效排名 / 月度库存 / 滞销清货",
     "definition": "没有匹配到负责人的业绩。Amazon EU 店铺（英国站固定归吴清栩）按本地 SKU 第一段品牌、OTH- 开头按第二段编号匹配；"
                   "其他 Amazon 店铺按店铺名第二段匹配 US 店铺规则；eBay 按品牌编码匹配（FLL、LEJ 归方黎力，CL 归陈丽）。"
                   "未配置规则、或负责人为空/待定/待到时计入未分配；只看该月份的负责人映射表。"},
    {"name": "净销售额（销售看板）", "page": "销售看板",
     "definition": "eBay 为财务月度数据的「净额（人民币）」，Amazon 为「总收款（人民币）」。"},
    {"name": "平台收入", "page": "销售看板", "definition": "财务月度数据的「平台收入-总(RMB)」。"},
    {"name": "毛利率（销售看板）", "page": "销售看板",
     "definition": "毛利润 ÷ 平台收入。多月份、多组别时先分别汇总分子和分母再相除，不对各月比率取平均。"},
    {"name": "退款率（销售看板）", "page": "销售看板",
     "definition": "退款金额 ÷ 销售总额，分子分母分别汇总后相除；退款金额为负数时比率也为负。"},
    {"name": "库存总货值", "page": "月度库存数据表",
     "definition": "本地期末在途成本 + 本地期末库存成本 + 海外仓与 FBA 期末在途成本 + 海外仓与 FBA 期末库存成本。"},
    {"name": "库存健康率", "page": "月度库存数据表",
     "definition": "库龄 181 天以上的去重 SKU 数 ÷（海外仓期末库存件数 + FBA 期末库存件数）；所需平台的库龄数据不全时为空。"},
    {"name": "建议补货量（eBay 补货 2.0）", "page": "eBay 补货",
     "definition": "按「补货公式配置」中当前启用的公式计算；销量基准为北京时间今天之前的近 90 天，拆成三个连续 30 天区间。"},
]


class MetricArgs(BaseModel):
    keyword: str | None = Field(None, max_length=40, description="指标名称关键词，如 毛利率、未分配；不填返回全部")


def metric_definitions(context: AgentContext, args: MetricArgs) -> ToolResult:
    keyword = (args.keyword or "").strip()
    rows = [m for m in METRICS if not keyword or keyword in m["name"] or keyword in m["definition"]]
    return ToolResult(
        title="指标口径", columns=[("name", "指标"), ("page", "所在页面"), ("definition", "口径")], rows=rows,
        source="系统计算逻辑", notes=[] if rows else [f"没有找到与「{keyword}」相关的指标说明"],
    )


# ---------------------------------------------------------------- 文档检索

REPO_ROOT = PROJECT_ROOT.parent
DOC_DIRS = [REPO_ROOT / "docs", PROJECT_ROOT / "docs", REPO_ROOT / "RuoYi-Vue-springboot3" / "docs",
            PROJECT_ROOT / "deploy"]
DOC_FILES = [REPO_ROOT / "README.md"]
SECRET_LINE = re.compile(r"(password|passwd|pwd|secret|token|api[_-]?key|密码|口令|密钥|秘钥|令牌)", re.IGNORECASE)
HEADING = re.compile(r"^#{1,4}\s+(.*)$")
CHUNK_CHARS = 1200


@dataclass(frozen=True)
class DocChunk:
    path: str
    heading: str
    text: str
    terms: Counter


def _terms(text: str) -> Counter:
    lowered = text.lower()
    words = re.findall(r"[a-z][a-z0-9_]{1,}", lowered)
    chinese = re.findall(r"[一-鿿]+", text)
    bigrams = [run[i:i + 2] for run in chinese for i in range(max(1, len(run) - 1))]
    return Counter(words + bigrams)


def _chunks_of(path: Path) -> list[DocChunk]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    relative = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    chunks, heading, buffer = [], path.stem, []

    def flush():
        text = "\n".join(buffer).strip()
        for start in range(0, len(text), CHUNK_CHARS):
            piece = text[start:start + CHUNK_CHARS]
            if piece.strip():
                chunks.append(DocChunk(relative, heading, piece, _terms(heading + " " + piece)))

    for line in lines:
        if SECRET_LINE.search(line):
            continue  # 含凭据字样的行不进入索引
        match = HEADING.match(line)
        if match:
            flush()
            heading, buffer = match.group(1).strip(), []
        else:
            buffer.append(line)
    flush()
    return chunks


class DocIndex:
    def __init__(self, paths: list[Path] | None = None):
        self._paths = paths
        self._chunks: list[DocChunk] | None = None
        self._df: Counter = Counter()
        self._lock = threading.Lock()

    def _load(self) -> list[DocChunk]:
        with self._lock:
            if self._chunks is None:
                files = self._paths if self._paths is not None else [
                    *[f for d in DOC_DIRS if d.is_dir() for f in sorted(d.rglob("*.md"))],
                    *[f for f in DOC_FILES if f.is_file()],
                ]
                chunks = [chunk for f in files for chunk in _chunks_of(f)]
                for chunk in chunks:
                    self._df.update(set(chunk.terms))
                self._chunks = chunks
        return self._chunks

    def search(self, query: str, limit: int = 5) -> list[tuple[float, DocChunk]]:
        chunks = self._load()
        query_terms = _terms(query)
        if not chunks or not query_terms:
            return []
        total = len(chunks)
        scored = []
        for chunk in chunks:
            score = 0.0
            length = sum(chunk.terms.values()) or 1
            for term in query_terms:
                tf = chunk.terms.get(term, 0)
                if tf:
                    idf = math.log(1 + (total - self._df[term] + 0.5) / (self._df[term] + 0.5))
                    score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / 400))
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: -item[0])
        return scored[:limit]


DOC_INDEX = DocIndex()


class DocSearchArgs(BaseModel):
    query: str = Field(..., min_length=2, max_length=80, description="要找的功能、流程或说明，如「负责人映射表怎么导入」")


def search_docs(context: AgentContext, args: DocSearchArgs) -> ToolResult:
    hits = DOC_INDEX.search(args.query)
    rows = [{"path": chunk.path, "heading": chunk.heading, "excerpt": chunk.text[:600], "score": round(score, 2)}
            for score, chunk in hits]
    return ToolResult(
        title=f"文档检索：{args.query}", columns=[("path", "文档"), ("heading", "章节"), ("excerpt", "内容摘录")],
        rows=rows, source="项目文档（docs、部署说明、README）",
        notes=[] if rows else ["没有找到相关文档；请说明文档里没有记载，不要凭推测回答"],
    )


KNOWLEDGE_TOOLS = [
    Tool("metric_definitions", "查询系统内各指标的计算口径（毛利率、未分配、库存总货值等），用户问「怎么算」「什么意思」时调用。",
         MetricArgs, metric_definitions, title="查询指标口径"),
    Tool("search_docs", "检索项目文档（功能说明、操作流程、部署说明），回答「怎么操作」「在哪里」「为什么」这类非数据问题。",
         DocSearchArgs, search_docs, title="检索项目文档"),
]
