"""
Synology NAS File Station API 客户端
- 登录/登出（session 管理）
- 按 SKU 搜索匹配文件夹（遍历 /JMH/供应链中心 下所有月份目录）
- 列出文件夹内图片文件
- 下载图片并缓存到本地

NAS 目录结构：
  /JMH/供应链中心/{YYYY.M}/{SKU_CODE}/  →  DSC_XXXX.JPG, Thumbs.db
  SKU_CODE 示例：BMW-30073-0010, DAS-10026-0128, FCA-50005-0021

MSKU → SKU 匹配规则：
  输入 MSKU: MH-US-30073-0010
  提取编号: 30073-0010 (或完整后缀)
  模糊匹配: 文件夹名包含该编号片段
"""

from __future__ import annotations

import fnmatch
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 图片扩展名
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
# 排除的系统文件
SKIP_FILES = {"thumbs.db", ".ds_store", "desktop.ini"}
# 白底图文件名关键词（含白底/主图/白背景/white背景等）
WHITE_BG_KEYWORDS = ["白底", "白色背景", "白背景", "主图", "面板", "画板",
                     "whitebg", "white-bg", "white_bg", "white-bk", "white background",
                     "wbg", "whitebgrd"]
# SKU 匹配打分：越长/越具体的片段得分越高，避免单纯数字片段误匹配其它 SKU
PATTERN_SCORES = {
    "full_sku": 100,      # 与文件夹名完全相等
    "full_msku": 95,      # 文件夹名包含完整 MSKU
    "brand_number_number": 80,  # 如 MCD-20236-0612
    "number_number": 60,  # 如 20236-0612
    "first_number": 30,   # 如 20236
    "other_number": 10,   # 其它 5 位以上数字片段
}
MIN_SCORE_IF_BETTER_EXISTS = 35
MIN_SCORE_WHEN_STRONG_MATCH = 50
STRONG_MATCH_SCORE = 60
_top_dir_cache: dict[str, tuple[float, list[dict]]] = {}
_top_dir_cache_lock = threading.Lock()
# ---- 路径编码修复 ----
# Synology File Station API 返回的路径可能存在 UTF-8 字节被错误解码为 Latin-1
# 示例: NAS 返回的路径可能出现乱码，需要此函数修复
# 修复: 将字符串按 Latin-1 编码回字节再按 UTF-8 解码
def _fix_nas_path(path: str) -> str:
    """修复 NAS 返回路径的编码问题"""
    if not path:
        return path
    try:
        # Latin-1 回编码 -> UTF-8 解码
        return path.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return path



@dataclass
class NasImageFile:
    """NAS 上的一张图片文件"""
    name: str
    path: str              # NAS 绝对路径，如 /JMH/供应链中心/2024.3/BMW-30073-0010/DSC_5987.JPG
    size: int
    folder_path: str       # 所在 SKU 文件夹路径
    sku_code: str          # 匹配到的 SKU 编码


@dataclass
class NasSkuMatch:
    """一个 SKU 文件夹的匹配结果"""
    sku_code: str           # 文件夹名，如 BMW-30073-0010
    folder_path: str        # NAS 路径，如 /JMH/供应链中心/2024.3/BMW-30073-0010
    month_dir: str          # 月份目录，如 2024.3
    images: list[NasImageFile] = field(default_factory=list)
    match_score: float = 0.0
    matched_patterns: list[str] = field(default_factory=list)


@dataclass
class NasSearchResult:
    """搜索结果"""
    msku: str               # 原始输入 MSKU
    matches: list[NasSkuMatch] = field(default_factory=list)
    total_images: int = 0
    search_time_ms: float = 0


class NasImageService:
    """Synology NAS File Station API 客户端"""

    def __init__(
        self,
        nas_url: str,
        username: str,
        password: str,
        cache_dir: Path,
        timeout: int = 30,
        base_path: str = "/JMH/供应链中心",
        search_workers: int = 6,
        image_collect_depth: int = 2,
        top_dir_cache_ttl: int = 600,
    ):
        self.nas_url = nas_url.rstrip("/")
        self.username = username
        self.password = password
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.base_path = base_path.rstrip("/") or "/JMH/供应链中心"
        self.search_workers = max(1, search_workers)
        self.image_collect_depth = max(0, image_collect_depth)
        self.top_dir_cache_ttl = max(60, top_dir_cache_ttl)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._client: Optional[httpx.Client] = None
        self._client_lock = threading.Lock()
        self._session_lock = threading.Lock()
        self._api_lock = threading.Lock()
        self._sid: Optional[str] = None

    @property
    def BASE_PATH(self) -> str:
        return self.base_path

    # ---- Session 管理 ----

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            with self._client_lock:
                if self._client is None or self._client.is_closed:
                    # QuickConnect 可能先将请求重定向到当前可用的 DSM 节点。
                    # 不跟随跳转时 auth.cgi 会落到中间节点并返回错误 400。
                    self._client = httpx.Client(
                        verify=False,
                        timeout=self.timeout,
                        follow_redirects=True,
                    )
        return self._client

    @property
    def _headers(self) -> dict:
        if not self._sid:
            raise RuntimeError("未登录 NAS，请先调用 login()")
        return {"X-SYNO-TOKEN": self._sid}

    def login(self) -> bool:
        """登录 DSM，返回是否成功"""
        client = self._get_client()
        try:
            r = client.get(
                f"{self.nas_url}/webapi/auth.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "version": "3",
                    "method": "login",
                    "account": self.username,
                    "passwd": self.password,
                    "session": "FileStation",
                    # QuickConnect 对 cookie 会话的兼容性不稳定：部分 DSM
                    # 节点首次请求会直接返回错误 400。当前客户端后续本来就
                    # 使用响应中的 sid 访问 File Station，因此明确请求 sid。
                    "format": "sid",
                },
            )
            data = r.json()
            if data.get("success"):
                self._sid = data["data"]["sid"]
                logger.info(f"NAS 登录成功, sid={self._sid[:16]}...")
                return True
            else:
                logger.error(f"NAS 登录失败: {data}")
                return False
        except Exception as exc:
            logger.error(f"NAS 登录异常: {exc}")
            return False

    def logout(self):
        """登出"""
        if self._sid and self._client and not self._client.is_closed:
            try:
                self._client.get(
                    f"{self.nas_url}/webapi/auth.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "version": "3",
                        "method": "logout",
                        "session": "FileStation",
                    },
                    headers=self._headers,
                )
            except Exception:
                pass
        self._sid = None
        logger.info("NAS 已登出")

    def ensure_login(self) -> bool:
        """确保已登录（幂等）"""
        if self._sid:
            return True
        with self._session_lock:
            if self._sid:
                return True
            return self.login()

    # ---- 目录操作 ----

    def _list_folder(self, folder_path: str, offset: int = 0, limit: int = 500) -> tuple[list[dict], int]:
        """
        列出目录内容。
        注意：这台 Synology 的 FileStation List API 使用 folder_path 参数（不是 path）。
        返回 (文件列表, 总数)
        """
        if not self.ensure_login():
            return [], 0

        client = self._get_client()
        with self._api_lock:
            r = client.get(
                f"{self.nas_url}/webapi/entry.cgi",
                params={
                    "api": "SYNO.FileStation.List",
                    "version": "2",
                    "method": "list",
                    "folder_path": folder_path,
                    "offset": offset,
                    "limit": limit,
                    "sort_by": "name",
                    "sort_direction": "asc",
                },
                headers=self._headers,
            )
        data = r.json()
        if data.get("success"):
            files = data["data"].get("files", [])
            total = data["data"].get("total", 0)
            for item in files:
                if "path" in item:
                    item["path"] = _fix_nas_path(item["path"])
            logger.debug(
                "NAS list folder: %s => total=%s returned=%s",
                folder_path,
                total,
                len(files),
            )
            return files, total
        logger.warning(f"列出目录失败 {folder_path}: {data.get('error')}")
        return [], 0

    def _list_all_folders(self, folder_path: str) -> tuple[list[dict], int]:
        """分页列出目录下所有直接子项，返回 (文件列表, 总数)。"""
        all_files: list[dict] = []
        offset = 0
        limit = 500
        total = 0
        while True:
            files, cur_total = self._list_folder(folder_path, offset=offset, limit=limit)
            total = cur_total or total
            if not files:
                break
            all_files.extend(files)
            if len(all_files) >= total:
                break
            offset += limit
        return all_files, total

    # ---- SKU 搜索核心逻辑 ----

    @staticmethod
    def extract_sku_patterns(msku: str) -> list[tuple[str, str, float]]:
        """
        从 MSKU 提取用于模糊匹配的候选模式，并附带匹配类型和基础得分。

        返回 [(pattern, pattern_type, base_score), ...]

        示例：
          MH-US-30073-0010 → [("MH-US-30073-0010", "full_msku", 95),
                              ("30073-0010", "number_number", 60),
                              ("30073", "first_number", 30)]
          BMW-30073-0010   → [("BMW-30073-0010", "full_msku", 95),
                              ("BMW-30073-0010", "brand_number_number", 80),
                              ("30073-0010", "number_number", 60),
                              ("30073", "first_number", 30)]
        """
        msku = msku.strip()
        raw_patterns: list[tuple[str, str, float]] = []

        # 1. 完整 MSKU
        if msku:
            raw_patterns.append((msku, "full_msku", PATTERN_SCORES["full_msku"]))

        # 2. 去掉常见站点/渠道前缀后的主体（如 MH-US-xxx -> xxx）
        parts = [p for p in msku.split("-") if p]
        if len(parts) >= 4:
            tail = "-".join(parts[1:])
            raw_patterns.append((tail, "full_msku", PATTERN_SCORES["full_msku"] - 5))
        if len(parts) >= 3:
            tail3 = "-".join(parts[-3:])
            raw_patterns.append((tail3, "brand_number_number", PATTERN_SCORES["brand_number_number"]))

        # 3. 品牌-数字-数字 格式（如 BMW-30073-0010）
        for brand_match in re.finditer(r"[A-Za-z]+-[0-9]+-[0-9]+", msku):
            raw_patterns.append(
                (brand_match.group(), "brand_number_number", PATTERN_SCORES["brand_number_number"])
            )

        # 4. 数字-数字 格式（如 30073-0010）
        num_match = re.search(r"[0-9]{4,}-[0-9]{3,}", msku)
        if num_match:
            num_code = num_match.group()
            raw_patterns.append((num_code, "number_number", PATTERN_SCORES["number_number"]))
            num_part = num_code.split("-")[0]
            raw_patterns.append((num_part, "first_number", PATTERN_SCORES["first_number"]))

        # 5. 其它纯数字段（5位以上），作为兜底但得分低
        first_num = num_match.group().split("-")[0] if num_match else None
        for m in re.finditer(r"[0-9]{5,}", msku):
            value = m.group()
            if value != first_num:
                raw_patterns.append((value, "other_number", PATTERN_SCORES["other_number"]))

        # 去重，保留最高得分
        seen: dict[str, tuple[str, float]] = {}
        ordered_types: list[str] = []
        for pat, ptype, score in raw_patterns:
            key = pat.lower()
            if key not in seen or seen[key][1] < score:
                seen[key] = (ptype, score)
                if key not in {k for k in seen if k != key}:
                    ordered_types.append(key)
        # 重新组装并保持原始优先级顺序
        unique: list[tuple[str, str, float]] = []
        visited: set[str] = set()
        for pat, ptype, score in raw_patterns:
            key = pat.lower()
            if key in visited:
                continue
            visited.add(key)
            unique.append((pat, seen[key][0], seen[key][1]))
        return unique

    @staticmethod
    def _pattern_boundary_regex(pattern: str) -> re.Pattern[str]:
        escaped = re.escape(pattern.lower())
        return re.compile(rf"(?:^|[-_/]){escaped}(?:$|[-_/])")

    @classmethod
    def _pattern_matches_name(cls, folder_name: str, pattern: str, pattern_type: str) -> bool:
        name_lower = folder_name.lower()
        pat_lower = pattern.lower()
        if name_lower == pat_lower:
            return True
        if pattern_type in {
            "full_sku",
            "full_msku",
            "brand_number_number",
            "number_number",
            "first_number",
            "other_number",
        }:
            return cls._pattern_boundary_regex(pattern).search(name_lower) is not None
        if pat_lower in name_lower:
            return True
        return fnmatch.fnmatch(name_lower, f"*{pat_lower}*")

    @classmethod
    def _score_folder_match(cls, folder_name: str, patterns: list[tuple[str, str, float]]) -> tuple[float, list[str]]:
        """
        根据候选模式给文件夹名打分，返回 (得分, [匹配到的模式列表])。
        """
        name_lower = folder_name.lower()
        best_score = 0.0
        matched: list[str] = []
        if patterns and name_lower == patterns[0][0].lower():
            return float(PATTERN_SCORES["full_sku"]), [patterns[0][0]]

        has_number_number = any(ptype == "number_number" for _, ptype, _ in patterns)
        has_brand_number = any(ptype == "brand_number_number" for _, ptype, _ in patterns)
        for pat, ptype, score in patterns:
            if has_number_number and ptype == "first_number":
                continue
            if (has_number_number or has_brand_number) and ptype == "other_number":
                continue
            if cls._pattern_matches_name(folder_name, pat, ptype):
                if score > best_score:
                    best_score = score
                    matched = [pat]
                elif score == best_score and pat not in matched:
                    matched.append(pat)
        return float(best_score), matched

    @staticmethod
    def _looks_like_sku_folder(name: str) -> bool:
        return bool(
            re.search(r"[A-Za-z0-9]+-[0-9]{3,}-[0-9]{2,}", name)
            or re.search(r"[0-9]{4,}-[0-9]{3,}", name)
        )

    def _get_top_dirs(self) -> list[dict]:
        cache_key = self.base_path
        now = time.monotonic()
        with _top_dir_cache_lock:
            cached = _top_dir_cache.get(cache_key)
            if cached and now - cached[0] < self.top_dir_cache_ttl:
                return cached[1]
        top_dirs, _ = self._list_all_folders(self.base_path)
        top_dirs = [d for d in top_dirs if d.get("isdir")]
        with _top_dir_cache_lock:
            _top_dir_cache[cache_key] = (now, top_dirs)
        return top_dirs

    @staticmethod
    def _should_drill_down(name: str) -> bool:
        if re.match(r"^\d{4}\.", name):
            return True
        keywords = ("设计", "资源", "AMZ", "套图", "供应链", "主图", "A+")
        return any(keyword in name for keyword in keywords)

    def _collect_candidate_folders(self, top_path: str, top_name: str) -> list[dict]:
        """收集顶层目录下可能的 SKU 文件夹（分组目录下再嵌套一层）。"""
        candidates: list[dict] = []
        children, _ = self._list_all_folders(top_path)
        for child in children:
            if not child.get("isdir"):
                continue
            child_name = child.get("name", "")
            if self._looks_like_sku_folder(child_name):
                child["month_dir"] = top_name
                candidates.append(child)
                continue
            if not self._should_drill_down(child_name):
                continue
            sub_children, _ = self._list_all_folders(child.get("path", ""))
            for sub in sub_children:
                if not sub.get("isdir"):
                    continue
                sub["month_dir"] = f"{top_name}/{child_name}"
                candidates.append(sub)
        return candidates

    @staticmethod
    def _extract_number_prefix(msku: str) -> str | None:
        num_match = re.search(r"([0-9]{4,})-([0-9]{3,})", msku)
        if not num_match:
            return None
        return f"{num_match.group(1)}-"

    @classmethod
    def _matches_number_prefix(cls, folder_name: str, prefix: str | None) -> bool:
        if not prefix:
            return False
        return re.search(
            rf"(?:^|[-_/]){re.escape(prefix)}[0-9]+",
            folder_name,
            re.IGNORECASE,
        ) is not None

    def _scan_top_dir(
        self,
        top_name: str,
        patterns: list[tuple[str, str, float]],
        number_prefix: str | None = None,
    ) -> list[NasSkuMatch]:
        top_path = f"{self.base_path}/{top_name}"
        matches: list[NasSkuMatch] = []
        try:
            candidate_folders = self._collect_candidate_folders(top_path, top_name)
        except Exception as exc:
            logger.warning("扫描顶层目录失败 %s: %s", top_path, exc)
            return matches

        scored_folders: list[tuple[float, list[str], dict]] = []
        for folder in candidate_folders:
            folder_name = folder.get("name", "")
            score, matched_pats = self._score_folder_match(folder_name, patterns)
            if score <= 0 and self._matches_number_prefix(folder_name, number_prefix):
                score = 55.0
                matched_pats = [number_prefix.rstrip("-")]
            if score <= 0:
                continue
            scored_folders.append((score, matched_pats, folder))

        if not scored_folders:
            return matches

        for score, matched_pats, folder in scored_folders:
            folder_name = folder.get("name", "")
            folder_path = folder.get("path", "")
            month_dir = folder.get("month_dir", top_name)
            try:
                image_files = self._collect_images_from_folder(folder_path, folder_name)
            except Exception as exc:
                logger.warning("收集图片失败 %s: %s", folder_path, exc)
                continue
            if not image_files:
                continue
            white_bg_count = sum(
                1 for img in image_files if self._is_white_bg_image(img.name)
            )
            white_bg_ratio = white_bg_count / len(image_files)
            final_score = score + white_bg_ratio * 20
            matches.append(
                NasSkuMatch(
                    sku_code=folder_name,
                    folder_path=folder_path,
                    month_dir=month_dir,
                    images=image_files,
                    match_score=round(final_score, 1),
                    matched_patterns=matched_pats,
                )
            )
        return matches

    @staticmethod
    def _filter_weak_matches(matches: list[NasSkuMatch]) -> list[NasSkuMatch]:
        if not matches:
            return matches
        matches.sort(key=lambda m: m.match_score, reverse=True)
        best_score = matches[0].match_score
        if best_score >= PATTERN_SCORES["brand_number_number"]:
            min_score = MIN_SCORE_IF_BETTER_EXISTS
        elif best_score >= STRONG_MATCH_SCORE:
            min_score = MIN_SCORE_WHEN_STRONG_MATCH
        else:
            return matches
        return [m for m in matches if m.match_score >= min_score]

    @staticmethod
    def _is_white_bg_image(name: str) -> bool:
        """判断文件名是否包含白底图/主图关键词（大小写不敏感）"""
        name_lower = name.lower()
        for kw in WHITE_BG_KEYWORDS:
            if kw in name_lower:
                return True
        # 额外：文件名以 "W-" 或 "W_" 开头（如 W-BMW-30073.jpg）
        # 且后面跟的不是 .w 扩展名（排除 Windows 文件名歧义）
        if name_lower.startswith("w-") or name_lower.startswith("w_"):
            return True
        return False

    def _collect_images_from_folder(
        self,
        folder_path: str,
        folder_name: str,
        max_depth: int | None = None,
    ) -> list[NasImageFile]:
        """
        收集指定文件夹内的图片文件，并可递归搜索子文件夹。

        设计部等目录经常把白底图放在 SKU 文件夹下的子目录中（如 jpg/、
        白底图/），因此需要往下探多级，避免漏掉白底图。
        全部分页遍历，防止文件夹图片过多时遗漏。
        """
        if max_depth is None:
            max_depth = self.image_collect_depth
        image_files: list[NasImageFile] = []
        seen_paths: set[str] = set()
        offset = 0
        limit = 500
        while True:
            try:
                entries, total = self._list_folder(folder_path, offset=offset, limit=limit)
            except Exception as exc:
                logger.warning(f"列出文件夹失败 {folder_path} (offset={offset}): {exc}")
                break
            if not entries:
                break
            for f in entries:
                fname = f.get("name", "")
                name_lower = fname.lower()
                fpath = _fix_nas_path(f.get("path", ""))
                if f.get("isdir"):
                    if max_depth > 0:
                        sub_images = self._collect_images_from_folder(
                            fpath,
                            folder_name,
                            max_depth=max_depth - 1,
                        )
                        for img in sub_images:
                            if img.path not in seen_paths:
                                seen_paths.add(img.path)
                                image_files.append(img)
                    continue
                ext = Path(name_lower).suffix
                if ext in IMAGE_EXTENSIONS and name_lower not in SKIP_FILES and fpath not in seen_paths:
                    seen_paths.add(fpath)
                    image_files.append(NasImageFile(
                        name=fname,
                        path=fpath,
                        size=f.get("size", 0),
                        folder_path=folder_path,
                        sku_code=folder_name,
                    ))
            if offset + limit >= total:
                break
            offset += limit
        return image_files

    def search_by_sku(self, msku: str) -> NasSearchResult:
        """
        按 MSKU 在供应链中心下搜索匹配的 SKU 文件夹及其图片。

        策略：
          1. 列出 base_path 下所有直接子目录（月份/资源目录）
          2. 并行扫描每个顶层目录下的 SKU 文件夹（支持分组目录再嵌套一层）
          3. 用边界感知的模糊匹配找到名称包含 SKU 关键字的文件夹
          4. 并行收集匹配文件夹内（及多层子文件夹）的图片文件
        """
        t0 = time.monotonic()
        result = NasSearchResult(msku=msku)
        patterns = self.extract_sku_patterns(msku)
        logger.info("搜索 NAS: MSKU=%s, 匹配模式=%s", msku, patterns)

        if not self.ensure_login():
            return result

        top_dirs = self._get_top_dirs()
        top_dir_names = [d.get("name", "") for d in top_dirs if d.get("name")]
        logger.info("顶层目录 (%s): %s...", len(top_dir_names), top_dir_names[:10])
        number_prefix = self._extract_number_prefix(msku)

        all_matches: list[NasSkuMatch] = []
        for top_name in top_dir_names:
            try:
                all_matches.extend(self._scan_top_dir(top_name, patterns, number_prefix))
            except Exception as exc:
                logger.warning("扫描顶层目录失败 %s: %s", top_name, exc)

        result.matches = self._filter_weak_matches(all_matches)
        result.total_images = sum(len(m.images) for m in result.matches)

        result.search_time_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "搜索完成: %s 个匹配文件夹, %s 张图, 耗时 %.0fms",
            len(result.matches),
            result.total_images,
            result.search_time_ms,
        )
        return result


    # ---- 图片下载与缓存 ----

    def download_thumbnail(self, nas_file_path: str, size: str = "small") -> Optional[Path]:
        """
        从 NAS 下载缩略图（优先使用 Synology Thumb API，失败则降级到下载原图）。
        与 download_image 独立，不影响 SOP 生成流程。

        size: Synology Thumb 尺寸 — small/medium/large
        """
        if not self.ensure_login():
            return None

        thumb_cache_dir = self.cache_dir / "thumbs"
        thumb_cache_dir.mkdir(parents=True, exist_ok=True)
        cache_name = ("thumb_" + nas_file_path.replace("/", "_").lstrip("_"))
        thumb_cache_path = thumb_cache_dir / cache_name
        # 确保后缀是 .jpg
        if thumb_cache_path.suffix.lower() not in (".jpg", ".jpeg"):
            thumb_cache_path = thumb_cache_path.with_suffix(".jpg")

        # 已有缓存且大于 1KB，直接返回
        if thumb_cache_path.exists() and thumb_cache_path.stat().st_size > 1024:
            return thumb_cache_path

        client = self._get_client()
        thumb_bytes = None

        # 方案1：尝试 Synology FileStation Thumb API
        try:
            r = client.get(
                f"{self.nas_url}/webapi/entry.cgi",
                params={
                    "api": "SYNO.FileStation.Thumb",
                    "version": "2",
                    "method": "get",
                    "path": nas_file_path,  # Thumb API 使用 path 参数
                    "size": size,
                },
                headers=self._headers,
                timeout=self.timeout,
            )
            if r.status_code == 200 and len(r.content) > 1024:
                ct = r.headers.get("content-type", "")
                if "image" in ct:
                    thumb_bytes = r.content
                    logger.debug(f"Synology Thumb API 成功: {nas_file_path} ({len(thumb_bytes)}B)")
        except Exception as exc:
            logger.debug(f"Synology Thumb API 失败，降级: {nas_file_path}: {exc}")

        # 方案2：降级 — 下载原图并生成缩略图
        if thumb_bytes is None:
            full_img = self.download_image(nas_file_path)
            if full_img is None:
                return None
            try:
                from PIL import Image
                img = Image.open(full_img)
                img.thumbnail((200, 200), Image.LANCZOS)
                img.save(thumb_cache_path, "JPEG", quality=60)
                return thumb_cache_path
            except Exception:
                return full_img  # 返回原图凑合

        # 保存 Synology Thumb API 返回的缩略图
        try:
            thumb_cache_path.write_bytes(thumb_bytes)
            return thumb_cache_path
        except Exception:
            return None

    def download_image(self, nas_file_path: str) -> Optional[Path]:
        """
        从 NAS 下载一张图片到本地缓存。
        返回本地缓存路径，失败返回 None。
        """
        if not self.ensure_login():
            return None

        cache_name = nas_file_path.replace("/", "_").lstrip("_")
        cache_path = self.cache_dir / cache_name
        cache_path_jpg = cache_path.with_suffix(".jpg")

        # 已缓存且非空则直接返回
        if cache_path_jpg.exists() and cache_path_jpg.stat().st_size > 0:
            return cache_path_jpg
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return cache_path

        client = self._get_client()
        temp_path = cache_path.with_name(
            f"{cache_path.name}.{threading.get_ident()}.part"
        )
        try:
            with client.stream(
                "GET",
                f"{self.nas_url}/webapi/entry.cgi",
                params={
                    "api": "SYNO.FileStation.Download",
                    "version": "2",
                    "method": "download",
                    "path": nas_file_path,
                },
                headers=self._headers,
            ) as response:
                if response.status_code != 200:
                    logger.warning(
                        "下载异常: %s, status=%s",
                        nas_file_path,
                        response.status_code,
                    )
                    return None
                size = 0
                with temp_path.open("wb") as target:
                    for chunk in response.iter_bytes(1024 * 1024):
                        target.write(chunk)
                        size += len(chunk)
            if size <= 1024:
                logger.warning("下载异常: %s, size=%s", nas_file_path, size)
                return None
            try:
                from PIL import Image

                with Image.open(temp_path) as img:
                    if img.mode in ("RGBA", "P", "LA"):
                        img = img.convert("RGB")
                    img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                    img.save(cache_path_jpg, "JPEG", quality=88, optimize=True)
                temp_path.unlink(missing_ok=True)
                logger.info(
                    "download+convert: %s -> %s (%sB)",
                    nas_file_path,
                    cache_path_jpg,
                    size,
                )
                return cache_path_jpg
            except Exception:
                temp_path.replace(cache_path)
                logger.info("download(raw): %s -> %s (%sB)", nas_file_path, cache_path, size)
                return cache_path
        except Exception as exc:
            logger.error(f"下载失败 {nas_file_path}: {exc}")
            return None
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def download_all_for_sku(self, msku: str) -> list[Path]:
        """
        搜索 SKU 并下载所有匹配图片到本地缓存。
        返回本地文件路径列表。
        """
        result = self.search_by_sku(msku)
        paths = []
        for match in result.matches:
            for img in match.images:
                local = self.download_image(img.path)
                if local:
                    paths.append(local)
        return paths

    # ---- 便捷方法 ----

    def get_main_image(self, msku: str) -> Optional[Path]:
        """获取 SKU 的主图（优先选白底图，其次取文件夹中第一张）"""
        result = self.search_by_sku(msku)
        all_images: list[NasImageFile] = []
        for match in result.matches:
            all_images.extend(match.images)

        if not all_images:
            return None

        # 优先找白底图
        for img in all_images:
            if self._is_white_bg_image(img.name):
                logger.info(f"NAS 主图命中白底图: {img.name}")
                return self.download_image(img.path)

        # 没有白底图，取第一张兜底
        logger.info(f"NAS 未找到白底图，取首张兜底: {all_images[0].name}")
        return self.download_image(all_images[0].path)

    def get_detail_images(self, msku: str, limit: int = 6) -> list[Path]:
        """获取 SKU 的细节图（跳过白底图/主图，最多返回 limit 张）"""
        result = self.search_by_sku(msku)
        all_images: list[NasImageFile] = []
        for match in result.matches:
            all_images.extend(match.images)

        # 排除白底图/主图，剩下的作为细节图
        detail_imgs = [img for img in all_images if not self._is_white_bg_image(img.name)]
        detail_imgs = detail_imgs[:limit]

        paths: list[Path] = []
        for img in detail_imgs:
            local = self.download_image(img.path)
            if local:
                paths.append(local)
        logger.info(f"NAS 细节图: {len(all_images)} 张总量, 排除白底后 {len(detail_imgs)} 张, 下载 {len(paths)} 张")
        return paths

    def close(self):
        """关闭连接"""
        self.logout()
        if self._client and not self._client.is_closed:
            self._client.close()
