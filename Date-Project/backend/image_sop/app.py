from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json as _json
import logging
import random
import re
import secrets
import shutil
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from urllib.parse import quote, unquote

from backend.image_sop.security import (
    browser_request_is_same_origin,
    client_is_internal,
    sanitize_health,
)

import httpx as _httpx_for_dl
from bs4 import BeautifulSoup
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel as _PydanticBaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import urljoin, urlparse

from backend.image_sop.config import get_settings
from backend.image_sop.repository import get_db, init_db
from backend.image_sop.models import (
    CopyBlock,
    EbayParseUrlRequest,
    ImageRequirement,
    ListingData,
    ProductAnalysis,
    SopExportRequest,
    SopResult,
)
from backend.image_sop.services.lingxing_auth import LingxingAuthClient, LingxingAuthError
from backend.image_sop.services.ai_service import AiService
from backend.image_sop.services.excel_service import ExcelService
from backend.image_sop.services.lingxing_service import LingxingService
from backend.image_sop.services.ebay_listing_service import EbayListingService
from backend.image_sop.services.nas_image_service import NasImageService
from backend.image_sop.services.web_image_search_service import (
    WebImageSearchService,
    generate_multi_angle_queries,
    refine_query_with_ai,
    build_deterministic_scene_queries,
    merge_scene_queries,
    _SCENE_TYPES,
)
from backend.config import settings as platform_settings

settings = get_settings()
logger = logging.getLogger(__name__)

settings.upload_path.mkdir(parents=True, exist_ok=True)
settings.export_path.mkdir(parents=True, exist_ok=True)
settings.web_ref_path.mkdir(parents=True, exist_ok=True)
if settings.nas_enabled:
    settings.nas_cache_path.mkdir(parents=True, exist_ok=True)


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return [str(item).strip() for item in value if str(item).strip()]


def _nas_media_url(kind: str, path: str) -> str:
    return f"/api/nas/{kind}?p={quote(path, safe='')}"


def _nas_ready() -> bool:
    """NAS 服务是否已配置且可用"""
    return settings.nas_enabled and bool(settings.nas_username)


def _parse_store_sid(raw: str | int | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        sid = int(raw)
    except (TypeError, ValueError):
        return None
    return sid if sid > 0 else None


def _listing_cache_version(listing: ListingData) -> str:
    if listing.source_updated_at:
        return listing.source_updated_at
    stable = {
        "asin": listing.asin,
        "title": listing.title,
        "bullet_points": listing.bullet_points,
        "description": listing.description,
        "keywords": listing.keywords,
        "oe_numbers": listing.oe_numbers,
    }
    raw = _json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _profile_cache_key(store_sid: int, sku: str) -> str:
    return f"{store_sid}:{sku.strip().lower()}"


def _copy_upload_to_path(
    upload: UploadFile,
    path: Path,
    max_bytes: int,
) -> int:
    upload.file.seek(0)
    total = 0
    try:
        with path.open("wb") as target:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("单张图片过大")
                target.write(chunk)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return total


def _safe_path_in_dir(base_dir: Path, filename: str) -> Path:
    """防止路径穿越，仅允许 base_dir 下的纯文件名"""
    name = Path(filename).name
    if not name or name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    resolved = (base_dir / name).resolve()
    if base_dir.resolve() not in resolved.parents and resolved != base_dir.resolve():
        raise HTTPException(status_code=403, detail="禁止访问")
    return resolved


def _assert_nas_media_path(path: str) -> str:
    """校验 NAS 媒体路径在配置的 base_path 范围内。"""
    from backend.image_sop.services.nas_image_service import _fix_nas_path

    decoded = _fix_nas_path(unquote(path or "").strip())
    if not decoded:
        raise HTTPException(status_code=400, detail="缺少图片路径参数 p")
    normalized = decoded.replace("\\", "/")
    if ".." in normalized:
        raise HTTPException(status_code=403, detail="非法 NAS 路径")
    base = (settings.nas_base_path or "/JMH/供应链中心").rstrip("/")
    if not (normalized == base or normalized.startswith(base + "/")):
        raise HTTPException(status_code=403, detail="NAS 路径不在允许范围内")
    return decoded


def _is_ebay_listing(listing: ListingData) -> bool:
    return "ebay" in (listing.data_source or "").lower()


def _make_nas_service() -> NasImageService:
    """创建 NAS 服务实例（统一工厂，消除 5 处重复代码）"""
    return NasImageService(
        nas_url=settings.nas_url,
        username=settings.nas_username,
        password=settings.nas_password,
        cache_dir=settings.nas_cache_path,
        timeout=settings.nas_timeout,
        base_path=settings.nas_base_path,
        search_workers=settings.nas_search_max_workers,
        image_collect_depth=settings.nas_image_collect_max_depth,
        top_dir_cache_ttl=settings.nas_search_top_dir_cache_ttl,
    )


app = FastAPI(title="跨境电商图片 SOP 生成系统", version="0.1.0")


class GenerationGate:
    def __init__(self, limit: int) -> None:
        self.limit = max(1, limit)
        self._semaphore: asyncio.Semaphore | None = None
        self._loop_id: int | None = None
        self.active = 0
        self.waiting = 0

    async def acquire(self) -> None:
        loop_id = id(asyncio.get_running_loop())
        if self._semaphore is None or self._loop_id != loop_id:
            self._semaphore = asyncio.Semaphore(self.limit)
            self._loop_id = loop_id
            self.active = 0
            self.waiting = 0
        self.waiting += 1
        try:
            await self._semaphore.acquire()
        except BaseException:
            self.waiting -= 1
            raise
        self.waiting -= 1
        self.active += 1

    def release(self) -> None:
        self.active = max(0, self.active - 1)
        if self._semaphore is not None:
            self._semaphore.release()

    def snapshot(self) -> dict[str, int]:
        return {
            "active": self.active,
            "waiting": self.waiting,
            "limit": self.limit,
        }


_generation_gate = GenerationGate(settings.sop_generation_max_concurrent)


class GenerationQueueMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not request.url.path.rstrip("/").endswith("/api/sop/generate"):
            return await call_next(request)
        await _generation_gate.acquire()
        try:
            return await call_next(request)
        finally:
            _generation_gate.release()


app.add_middleware(GenerationQueueMiddleware)


class ImageSopInternalAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path.rstrip("/")
        if "/api/" not in path and not path.endswith("/api"):
            return await call_next(request)
        configured = platform_settings.python_internal_api_token
        provided = request.headers.get("X-Internal-Token", "")
        direct_browser = browser_request_is_same_origin(
            request.headers.get("host", ""),
            request.headers.get("referer", ""),
            request.headers.get("sec-fetch-site", ""),
        )
        if configured:
            token_valid = bool(provided) and secrets.compare_digest(
                provided, configured
            )
            if not token_valid and not direct_browser:
                return Response(
                    content='{"code":401,"message":"内部接口令牌无效","data":null,"request_id":""}',
                    status_code=401,
                    media_type="application/json",
                )
        else:
            client_host = request.client.host if request.client else ""
            if (
                client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}
                and not direct_browser
            ):
                return Response(
                    content='{"code":403,"message":"未配置内部接口令牌时，仅允许本机访问","data":null,"request_id":""}',
                    status_code=403,
                    media_type="application/json",
                )
        return await call_next(request)


app.add_middleware(ImageSopInternalAccessMiddleware)

class CharsetMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type or "application/json" in content_type:
            if "charset" not in content_type:
                response.headers["content-type"] = f"{content_type}; charset=utf-8"
        return response

app.add_middleware(CharsetMiddleware)

_WEB_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "image-sop"

if _WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")

# ── 公共常量 ──
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


async def _validate_external_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL 必须使用 http 或 https")
    try:
        addresses = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)),
        )
    except OSError as exc:
        raise HTTPException(status_code=400, detail="目标域名无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise HTTPException(status_code=403, detail="禁止访问本机、内网或保留地址")
    return raw_url


async def _safe_external_get(client: _httpx_for_dl.AsyncClient, raw_url: str):
    current = raw_url
    for _ in range(6):
        await _validate_external_url(current)
        response = await client.get(current, follow_redirects=False)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        current = urljoin(current, location)
    raise HTTPException(status_code=400, detail="URL 重定向次数过多")


@app.get("/")
@app.get("/index.html", include_in_schema=False)
async def index() -> FileResponse:
    html = _WEB_DIR / "index.html"
    if not html.exists():
        raise HTTPException(status_code=404, detail="web/index.html 不存在")
    return FileResponse(
        html,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


async def _lingxing_health() -> dict:
    if settings.lingxing_use_mock:
        return {"configured": True, "token_ok": True, "error": None, "mock": True}
    if not settings.lingxing_app_key or not settings.lingxing_app_secret:
        return {
            "configured": False,
            "token_ok": False,
            "error": "lingxing_app_key/secret not configured",
        }
    client = LingxingAuthClient(
        settings.lingxing_app_key,
        settings.lingxing_app_secret,
        settings.lingxing_api_base,
    )
    try:
        await client._fetch_access_token()
        return {"configured": True, "token_ok": True, "error": None}
    except LingxingAuthError as exc:
        return {"configured": True, "token_ok": False, "error": str(exc)}
    except Exception as exc:
        return {"configured": True, "token_ok": False, "error": str(exc)}


@app.get("/api/health")
async def health(request: Request):
    payload = {
        "ok": True,
        "service": "sop",
        "port": 8010,
        "lingxing": await _lingxing_health(),
    }
    if client_is_internal(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for", ""),
    ):
        return payload
    return sanitize_health(payload)


@app.get("/api/sop/generation-status")
async def generation_status() -> dict[str, int]:
    return _generation_gate.snapshot()


@app.get("/api/lingxing/stores")
async def list_lingxing_stores() -> dict[str, object]:
    """获取全部亚马逊店铺列表（领星 seller/lists）。"""
    service = LingxingService(settings)
    try:
        stores = await service.list_amazon_stores()
    except LingxingAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"店铺列表获取失败: {getattr(exc, 'message', str(exc))}",
        ) from exc
    default_sid = settings.lingxing_default_sid
    if default_sid <= 0 and stores:
        default_sid = int(stores[0]["sid"])
    return {"stores": stores, "default_sid": default_sid}


def _premium_detail_design_request(detail_count: int) -> str:
    if detail_count >= 4:
        return (
            "将4张产品局部细节图按2×2网格拼接为一张完整的高级A+ PRODUCT DETAILS图："
            "顶部放置大写标题'PRODUCT DETAILS'；4张局部图均匀分布，等比例缩放并居中裁剪填满网格，"
            "统一圆角边框和间距；背景使用深色或品牌色渐变，突出产品细节与金属/塑料质感。"
        )
    if detail_count == 3:
        return (
            "将3张产品局部细节图横向三等分拼接为一张完整的高级A+ PRODUCT DETAILS图："
            "顶部放置大写标题'PRODUCT DETAILS'；3张图等比例缩放居中裁剪，统一间距与圆角边框；背景使用深色或品牌色。"
        )
    if detail_count == 2:
        return (
            "将2张产品局部细节图左右并排拼接为一张完整的高级A+ PRODUCT DETAILS图："
            "顶部放置大写标题'PRODUCT DETAILS'；2张图各占一半宽度，等比例缩放居中裁剪，统一间距；背景使用深色或品牌色。"
        )
    return (
        "将1张产品局部细节图作为高级A+ PRODUCT DETAILS图的主体："
        "图片居中放大展示，顶部放置大写标题'PRODUCT DETAILS'；背景使用深色或品牌色，突出产品细节。"
    )


def _append_premium_detail_local_row(
    premium_image_requirements: list[ImageRequirement],
    detail_local_urls: list[str],
    premium_design_request: str,
) -> list[ImageRequirement]:
    if not detail_local_urls:
        return premium_image_requirements
    premium_product_details_req = ImageRequirement(
        index=len(premium_image_requirements) + 1,
        theme="PRODUCT DETAILS",
        size=settings.sop_premium_image_size,
        copy_text="",
        design_request=premium_design_request,
        reference_image=detail_local_urls[0],
        reference_images=list(detail_local_urls),
        reference_source="detail_local",
    )
    updated = list(premium_image_requirements)
    if len(updated) >= 2:
        updated.insert(-1, premium_product_details_req)
    else:
        updated.append(premium_product_details_req)
    for i, req in enumerate(updated, 1):
        req.index = i
    return updated


def _parse_mix_image_link_flags(raw: str, mix_count: int) -> list[bool]:
    if mix_count <= 0:
        return []
    if not (raw or "").strip():
        return [False] * mix_count
    try:
        sources = _json.loads(raw)
    except Exception:
        return [False] * mix_count
    if not isinstance(sources, list):
        return [False] * mix_count
    flags = [str(item).strip().lower() == "link" for item in sources]
    if len(flags) < mix_count:
        flags.extend([False] * (mix_count - len(flags)))
    return flags[:mix_count]


def _build_scene_link_sources(mix_link_flags: list[bool], ai_mix_count: int) -> list[bool]:
    return list(mix_link_flags) + ([False] * max(0, ai_mix_count))


async def _pregenerate_premium_background(
    draft_id: str,
    normalized_sku: str,
    listing: ListingData,
    primary_main_url: str,
    primary_main_path: Path,
    detail_reference_urls: list[str],
    scene_reference_urls: list[str],
    has_operator_references: bool,
    product_analysis: ProductAnalysis,
    copy: CopyBlock,
    detail_local_urls: list[str],
    premium_design_request: str,
    scene_link_sources: list[bool] | None = None,
) -> None:
    """后台预生成高级A+，不阻塞主流程返回。"""
    product_info = getattr(product_analysis, "_product_info", None)
    ai_service = AiService(settings)
    try:
        premium_analysis, premium_copy, premium_image_requirements, _ = (
            await ai_service.generate_premium_copy_and_requirements(
                listing=listing,
                main_image=primary_main_url,
                detail_reference_urls=detail_reference_urls,
                scene_reference_urls=scene_reference_urls,
                has_operator_references=has_operator_references,
                sku=normalized_sku,
                main_image_path=primary_main_path,
                standard_copy=copy,
                standard_analysis=product_analysis,
                product_info=product_info if isinstance(product_info, dict) else None,
                scene_link_sources=scene_link_sources,
            )
        )
        if detail_local_urls:
            premium_image_requirements = _append_premium_detail_local_row(
                premium_image_requirements,
                detail_local_urls,
                premium_design_request,
            )

        loop = asyncio.get_running_loop()
        draft = await loop.run_in_executor(None, get_db().get_draft, draft_id)
        if not draft:
            logger.info("后台高级A+跳过：草稿 %s 已不存在", draft_id)
            return

        draft["premium_analysis"] = premium_analysis.model_dump()
        draft["premium_copy_block"] = premium_copy.model_dump()
        draft["premium_image_requirements"] = [
            item.model_dump() for item in premium_image_requirements
        ]
        draft["premium_status"] = "ready"
        await loop.run_in_executor(
            None, get_db().save_draft, draft_id, normalized_sku, draft
        )
        logger.info("后台高级A+预生成完成 SKU=%s draft=%s", normalized_sku, draft_id[:8])
    except Exception:
        import traceback as _tb
        logger.info(
            "后台高级A+预生成失败（导出时将实时生成）SKU=%s:\n%s",
            normalized_sku,
            _tb.format_exc(),
        )
        try:
            loop = asyncio.get_running_loop()
            draft = await loop.run_in_executor(None, get_db().get_draft, draft_id)
            if draft:
                draft["premium_status"] = "failed"
                await loop.run_in_executor(
                    None, get_db().save_draft, draft_id, normalized_sku, draft
                )
        except Exception:
            logger.debug("更新 premium_status=failed 时出错", exc_info=True)


@app.post("/api/sop/generate", response_model=SopResult)
async def generate_sop(
    background_tasks: BackgroundTasks,
    request: Request,
    sku: str = Form(...),
    sid: int | None = Form(None),
    source_mode: str = Form(default="sku"),
    listing_data_json: str = Form(default=""),
    main_images: list[UploadFile] = File(default=[]),
    reference_images: list[UploadFile] = File(default=[]),
    mix_images: list[UploadFile] = File(default=[]),
    detail_local_images: list[UploadFile] = File(default=[]),
    ai_mix_images: list[str] = Form(default=[]),
    mix_image_sources: str = Form(default=""),
    nas_main_image: str = Form(default=""),
    nas_reference_images: list[str] = Form(default=[]),
    nas_detail_local_images: list[str] = Form(default=[]),
) -> SopResult:
    request_started = time.perf_counter()
    form = await request.form()
    nas_detail_local_images = _as_str_list(nas_detail_local_images)
    form_dtl = [str(v).strip() for v in form.getlist("nas_detail_local_images") if str(v).strip()]
    if len(form_dtl) > len(nas_detail_local_images):
        nas_detail_local_images = form_dtl
    nas_reference_images = _as_str_list(nas_reference_images)
    form_refs = [str(v).strip() for v in form.getlist("nas_reference_images") if str(v).strip()]
    if len(form_refs) > len(nas_reference_images):
        nas_reference_images = form_refs
    logger.info(
        "SOP generate form: sku=%s nas_detail_local=%d nas_ref=%d dtl_upload=%d nas_dtl=%s",
        sku,
        len(nas_detail_local_images),
        len(nas_reference_images),
        len([item for item in detail_local_images if getattr(item, "filename", None)]),
        nas_detail_local_images,
    )
    normalized_sku = sku.strip()
    if not normalized_sku:
        raise HTTPException(status_code=400, detail="SKU 不能为空")
    mode = (source_mode or "sku").strip().lower()
    if mode not in {"sku", "ebay"}:
        raise HTTPException(status_code=400, detail="source_mode 必须是 sku 或 ebay")

    if mode == "ebay":
        store_sid = _parse_store_sid(sid) or 0
    else:
        store_sid = _parse_store_sid(sid)
        if store_sid is None:
            raise HTTPException(status_code=400, detail="请选择亚马逊店铺")
        if settings.lingxing_use_mock:
            raise HTTPException(status_code=400, detail="当前为Mock模式，请配置真实领星参数并关闭 LINGXING_USE_MOCK")

    valid_main_images = [item for item in main_images if item.filename]

    # ---- NAS 图片下载（线程池并发，不阻塞事件循环）----
    nas_service = None
    nas_downloaded_main = None
    nas_downloaded_refs: dict[str, Path] = {}
    nas_downloaded_detail_locals: dict[str, Path] = {}

    if _nas_ready() and (nas_main_image or nas_reference_images or nas_detail_local_images):
        nas_service = _make_nas_service()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, nas_service.ensure_login)
        download_limit = max(1, settings.nas_download_max_concurrent)
        download_semaphore = asyncio.Semaphore(download_limit)

        async def _download_nas(path: str) -> tuple[str, Path | None]:
            async with download_semaphore:
                local = await loop.run_in_executor(
                    None,
                    nas_service.download_image,
                    path,
                )
                return path, local

        requested_paths = list(
            dict.fromkeys(
                ([nas_main_image] if nas_main_image else [])
                + list(nas_reference_images)
                + list(nas_detail_local_images)
            )
        )
        started_at = time.perf_counter()
        results = await asyncio.gather(
            *[_download_nas(path) for path in requested_paths],
            return_exceptions=True,
        )
        downloaded: dict[str, Path] = {}
        download_errors: list[str] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("NAS 图片下载异常: %s", result)
                download_errors.append(str(result))
                continue
            path, local = result
            if local:
                downloaded[path] = local
        logger.info(
            "[SOP-TIMING] phase=nas_download files=%d success=%d total_ms=%.0f",
            len(requested_paths),
            len(downloaded),
            (time.perf_counter() - started_at) * 1000,
        )
        missing_paths = [path for path in requested_paths if path not in downloaded]
        if missing_paths:
            missing_names = [Path(path).name for path in missing_paths]
            try:
                nas_service.close()
            except Exception:
                logger.debug("NAS service close 时出现异常（不影响主流程）")
            nas_service = None
            extra = f"；错误: {download_errors[0]}" if download_errors else ""
            raise HTTPException(
                status_code=502,
                detail=(
                    f"NAS 图片下载失败 {len(missing_paths)}/{len(requested_paths)} 张："
                    + "、".join(missing_names[:8])
                    + ("…" if len(missing_names) > 8 else "")
                    + extra
                    + "。请重试或改选其他图片后再生成。"
                ),
            )
        nas_downloaded_main = downloaded.get(nas_main_image) if nas_main_image else None
        nas_downloaded_refs = {
            path: downloaded[path]
            for path in nas_reference_images
            if path in downloaded
        }
        nas_downloaded_detail_locals = {
            path: downloaded[path]
            for path in nas_detail_local_images
            if path in downloaded
        }

    # 如果没有上传主图但有 NAS 主图，用 NAS 主图替代
    if not valid_main_images and nas_downloaded_main:
        class _PseudoUploadFile:
            def __init__(self, path: Path):
                self.filename = path.name
                self._path = path
            async def read(self) -> bytes:
                return self._path.read_bytes()
        valid_main_images = [_PseudoUploadFile(nas_downloaded_main)]

    uploaded_bytes = 0
    max_file_bytes = max(1, settings.upload_max_file_mb) * 1024 * 1024
    max_total_bytes = max(1, settings.upload_max_total_mb) * 1024 * 1024
    upload_bytes_lock = asyncio.Lock()

    async def save_upload(upload: UploadFile, prefix: str) -> tuple[str, Path]:
        nonlocal uploaded_bytes
        suffix = Path(upload.filename or "").suffix or ".jpg"
        upload_name = f"{prefix}_{uuid4().hex[:8]}{suffix}"
        path = settings.upload_path / upload_name
        try:
            if hasattr(upload, "file"):
                size = await asyncio.get_running_loop().run_in_executor(
                    None,
                    _copy_upload_to_path,
                    upload,
                    path,
                    max_file_bytes,
                )
            else:
                content = await upload.read()
                size = len(content)
                if size > max_file_bytes:
                    raise ValueError("单张图片过大")
                path.write_bytes(content)
            async with upload_bytes_lock:
                uploaded_bytes += size
                if uploaded_bytes > max_total_bytes:
                    try:
                        path.unlink()
                    except OSError:
                        pass
                    uploaded_bytes -= size
                    raise ValueError("本次上传图片总大小过大")
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        return upload_name, path

    main_urls: list[str] = []
    upload_files: dict[str, Path] = {}
    main_save_tasks = [
        save_upload(main_upload, f"{normalized_sku}_main{idx + 1}")
        for idx, main_upload in enumerate(valid_main_images)
    ]
    if main_save_tasks:
        main_saved = await asyncio.gather(*main_save_tasks)
        for main_name, main_path in main_saved:
            main_urls.append(f"/api/uploads/{main_name}")
            upload_files[main_name] = main_path

    primary_main_url = main_urls[0] if main_urls else ""

    # ── 细节图池（产品特写，运营上传/NAS参考图）──
    detail_reference_urls: list[str] = list(main_urls[1:] if len(main_urls) > 1 else [])
    for ref_path, ref_local in nas_downloaded_refs.items():
        ref_url = _nas_media_url("image", ref_path)
        detail_reference_urls.append(ref_url)
        upload_files[ref_local.name] = ref_local
    ref_save_tasks = [
        save_upload(ref_upload, f"{normalized_sku}_ref{idx + 1}")
        for idx, ref_upload in enumerate(reference_images)
        if ref_upload.filename
    ]
    if ref_save_tasks:
        ref_saved = await asyncio.gather(*ref_save_tasks)
        for ref_name, ref_path in ref_saved:
            detail_reference_urls.append(f"/api/uploads/{ref_name}")
            upload_files[ref_name] = ref_path

    # ── 场景物品图池（使用环境/安装场景，运营上传+AI搜索+链接获取）──
    scene_reference_urls: list[str] = []
    mix_save_tasks = [
        save_upload(mix_upload, f"{normalized_sku}_mix{idx + 1}")
        for idx, mix_upload in enumerate(mix_images)
        if mix_upload.filename
    ]
    if mix_save_tasks:
        mix_saved = await asyncio.gather(*mix_save_tasks)
        for mix_name, mix_path in mix_saved:
            scene_reference_urls.append(f"/api/uploads/{mix_name}")
            upload_files[mix_name] = mix_path
    mix_upload_count = len([u for u in mix_images if u.filename])
    mix_link_flags = _parse_mix_image_link_flags(mix_image_sources, mix_upload_count)
    for filename in ai_mix_images:
        ai_path = settings.web_ref_path / filename
        if ai_path.exists():
            scene_reference_urls.append(f"/api/web-refs/{filename}")
            upload_files[filename] = ai_path

    scene_link_sources = _build_scene_link_sources(mix_link_flags, len(ai_mix_images))

    # ── 局部图池（产品详情图，可选，用于 Excel 额外展示行）──
    detail_local_urls: list[str] = []
    for idx, (dtl_path, dtl_local) in enumerate(nas_downloaded_detail_locals.items(), start=1):
        suffix = dtl_local.suffix or ".jpg"
        upload_name = f"{normalized_sku}_dtl_nas{idx}_{uuid4().hex[:8]}{suffix}"
        dest = settings.upload_path / upload_name
        try:
            shutil.copy2(dtl_local, dest)
            stored = dest
        except Exception:
            stored = dtl_local
            upload_name = dtl_local.name
        detail_local_urls.append(f"/api/uploads/{upload_name}")
        upload_files[upload_name] = stored
        upload_files[dtl_local.name] = stored
        orig_cache_name = dtl_path.replace("/", "_").lstrip("_")
        if orig_cache_name and orig_cache_name not in upload_files:
            upload_files[orig_cache_name] = stored
    dtl_save_tasks = [
        save_upload(dtl_upload, f"{normalized_sku}_dtl{idx + 1}")
        for idx, dtl_upload in enumerate(detail_local_images)
        if dtl_upload.filename
    ]
    if dtl_save_tasks:
        dtl_saved = await asyncio.gather(*dtl_save_tasks)
        for dtl_name, dtl_path in dtl_saved:
            detail_local_urls.append(f"/api/uploads/{dtl_name}")
            upload_files[dtl_name] = dtl_path
    logger.info(
        "局部图入库: nas_in=%d upload_in=%d urls=%d files=%s",
        len(nas_detail_local_images),
        len([item for item in detail_local_images if item.filename]),
        len(detail_local_urls),
        [Path(u).name for u in detail_local_urls],
    )

    has_operator_references = (len(detail_reference_urls) + len(scene_reference_urls)) > 0

    if nas_downloaded_main and not primary_main_url:
        primary_main_url = _nas_media_url("image", nas_main_image)
    if not primary_main_url:
        raise HTTPException(status_code=400, detail="请至少上传一张主图或从 NAS 选择主图")

    # 验证细节图+场景物品图总数 >= 6
    total_refs = len(detail_reference_urls) + len(scene_reference_urls)
    if total_refs < 6:
        raise HTTPException(
            status_code=400,
            detail=(
                f"细节图+场景物品图合计至少需要 6 张"
                f"（当前细节图 {len(detail_reference_urls)} 张 + "
                f"场景物品图 {len(scene_reference_urls)} 张 = {total_refs} 张，"
                f"还缺 {6 - total_refs} 张）"
            ),
        )

    primary_main_name = primary_main_url.rsplit("/", 1)[-1]
    if primary_main_name not in upload_files and nas_downloaded_main:
        upload_files[primary_main_name] = nas_downloaded_main
    primary_main_path = upload_files.get(primary_main_name)
    if not primary_main_path:
        raise HTTPException(status_code=400, detail="主图文件未找到")

    lingxing_service = LingxingService(settings)
    ai_service = AiService(settings)

    try:
        listing_started = time.perf_counter()
        if mode == "ebay":
            if not listing_data_json.strip():
                raise HTTPException(status_code=400, detail="eBay 模式需要提供 listing_data")
            try:
                listing = ListingData.model_validate(_json.loads(listing_data_json))
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"listing_data 格式无效: {exc}") from exc
            listing = listing.model_copy(update={"sku": normalized_sku, "asin": ""})
            listing_version = _listing_cache_version(listing)
            cache_key = f"ebay:{normalized_sku.strip().lower()}:{listing_version}"
            logger.info(
                "[SOP-TIMING] phase=listing mode=ebay sku=%s total_ms=%.0f",
                normalized_sku,
                (time.perf_counter() - listing_started) * 1000,
            )
        else:
            listing = await lingxing_service.get_listing_by_sku(normalized_sku, sid=store_sid)
            listing_version = _listing_cache_version(listing)
            cache_key = _profile_cache_key(store_sid, normalized_sku)
            logger.info(
                "[SOP-TIMING] phase=listing sid=%s sku=%s total_ms=%.0f",
                store_sid,
                normalized_sku,
                (time.perf_counter() - listing_started) * 1000,
            )
        cache_max_age = max(1, settings.ai_profile_cache_ttl_hours) * 3600
        loop = asyncio.get_running_loop()
        cached_product_info = await loop.run_in_executor(
            None,
            get_db().get_ai_profile,
            cache_key,
            listing_version,
            cache_max_age,
        )
        logger.info(
            "[AI-CACHE] sid=%s sku=%s hit=%s version=%s",
            store_sid,
            normalized_sku,
            bool(cached_product_info),
            listing_version[:24],
        )
        ai_started = time.perf_counter()
        product_analysis, copy, image_requirements, web_ref_files = (
            await ai_service.generate_copy_and_requirements(
                listing=listing,
                main_image=primary_main_url,
                detail_reference_urls=detail_reference_urls,
                scene_reference_urls=scene_reference_urls,
                has_operator_references=has_operator_references,
                sku=normalized_sku,
                main_image_path=primary_main_path,
                product_info=cached_product_info,
                scene_link_sources=scene_link_sources,
            )
        )
        logger.info(
            "[SOP-TIMING] phase=standard_ai sid=%s sku=%s total_ms=%.0f",
            store_sid,
            normalized_sku,
            (time.perf_counter() - ai_started) * 1000,
        )
        product_info = getattr(product_analysis, "_product_info", None)
        if isinstance(product_info, dict) and product_info.get("product_name"):
            await loop.run_in_executor(
                None,
                get_db().save_ai_profile,
                cache_key,
                listing_version,
                product_info,
            )
        for name, path in web_ref_files.items():
            upload_files[name] = path

        # ── 追加局部图行（如果运营提供了局部图）──
        premium_design_request = ""
        if detail_local_urls:
            detail_count = len(detail_local_urls)
            if detail_count >= 4:
                standard_design_request = (
                    "将运营提供的4张产品局部细节图按2×2网格拼接为一张完整的PRODUCT DETAILS展示图："
                    "顶部居中放置大写标题'PRODUCT DETAILS'；4张局部图均匀分布于下方，每张图等比例缩放并居中裁剪填满各自网格，"
                    "保持统一圆角边框和间距；背景采用深色或浅灰纯色以突出产品质感，整体构图简洁专业。"
                )
                premium_design_request = _premium_detail_design_request(detail_count)
            elif detail_count == 3:
                standard_design_request = (
                    "将运营提供的3张产品局部细节图按一排横向拼接（左中右三等分）为一张完整的PRODUCT DETAILS展示图："
                    "顶部居中放置大写标题'PRODUCT DETAILS'；3张局部图等比例缩放并居中裁剪，保持统一间距和圆角边框；"
                    "背景采用纯色，突出产品细节。"
                )
                premium_design_request = _premium_detail_design_request(detail_count)
            elif detail_count == 2:
                standard_design_request = (
                    "将运营提供的2张产品局部细节图按左右并排拼接为一张完整的PRODUCT DETAILS展示图："
                    "顶部居中放置大写标题'PRODUCT DETAILS'；2张局部图各占一半宽度，等比例缩放并居中裁剪，保持统一间距；"
                    "背景采用纯色，突出产品细节。"
                )
                premium_design_request = _premium_detail_design_request(detail_count)
            else:
                standard_design_request = (
                    "将运营提供的1张产品局部细节图作为PRODUCT DETAILS展示图的主体："
                    "图片居中放大展示，顶部放置大写标题'PRODUCT DETAILS'；背景采用纯色，突出产品细节质感。"
                )
                premium_design_request = _premium_detail_design_request(detail_count)

            product_details_req = ImageRequirement(
                index=len(image_requirements) + 1,
                theme="PRODUCT DETAILS",
                size=settings.sop_image_size,
                copy_text="PRODUCT DETAILS",
                design_request=standard_design_request,
                reference_image=detail_local_urls[0],
                reference_images=list(detail_local_urls),
                reference_source="detail_local",
            )
            image_requirements.append(product_details_req)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        import traceback as _tb
        logger.exception(f"生成 SOP 异常: {exc}")
        msg = getattr(exc, "message", None) or str(exc) or type(exc).__name__
        raise HTTPException(status_code=500, detail=f"生成失败: {msg}") from exc
    finally:
        if nas_service:
            try:
                nas_service.close()
            except Exception:
                logger.debug("NAS service close 时出现异常（不影响主流程）")

    draft_id = uuid4().hex
    draft_data = {
        "sku": normalized_sku,
        "store_sid": store_sid,
        "upload_path": str(primary_main_path),
        "upload_files": {name: str(path) for name, path in upload_files.items()},
        "web_ref_files": {name: str(path) for name, path in web_ref_files.items()},
        "copy_block": copy.model_dump(),
        "product_analysis": product_analysis.model_dump(),
        "image_requirements": [item.model_dump() for item in image_requirements],
        "detail_local_urls": detail_local_urls,
        "listing_data": listing.model_dump(),
        "scene_link_sources": scene_link_sources,
        "premium_analysis": {},
        "premium_copy_block": {},
        "premium_image_requirements": [],
        "premium_status": "pending",
    }
    await asyncio.get_running_loop().run_in_executor(
        None, get_db().save_draft, draft_id, normalized_sku, draft_data
    )

    background_tasks.add_task(
        _pregenerate_premium_background,
        draft_id,
        normalized_sku,
        listing,
        primary_main_url,
        primary_main_path,
        detail_reference_urls,
        scene_reference_urls,
        has_operator_references,
        product_analysis,
        copy,
        detail_local_urls,
        premium_design_request,
        scene_link_sources,
    )
    logger.info(
        "[SOP-TIMING] phase=request_complete sid=%s sku=%s total_ms=%.0f",
        store_sid,
        normalized_sku,
        (time.perf_counter() - request_started) * 1000,
    )

    return SopResult(
        sku=normalized_sku,
        draft_id=draft_id,
        listing_data=listing,
        product_analysis=product_analysis,
        copy_block=copy,
        image_requirements=image_requirements,
        excel_file="",
        ai_provider=settings.active_ai_provider,
        scrape_feedback={
            "status": listing.scrape_status,
            "reason": listing.scrape_reason,
            "action": listing.scrape_action,
        },
    )


@app.get("/api/sop/premium-status")
async def sop_premium_status(draft_id: str) -> dict[str, object]:
    """高级 A+ 后台预生成是否就绪。"""
    normalized = draft_id.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="draft_id 不能为空")
    loop = asyncio.get_running_loop()
    draft = await loop.run_in_executor(None, get_db().get_draft, normalized)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在或已过期")
    premium_reqs = draft.get("premium_image_requirements") or []
    status = str(draft.get("premium_status") or ("ready" if premium_reqs else "pending"))
    return {
        "draft_id": normalized,
        "ready": bool(premium_reqs),
        "status": status,
        "premium_count": len(premium_reqs),
    }


@app.post("/api/sop/export")
async def export_sop(payload: SopExportRequest) -> dict[str, str]:
    loop = asyncio.get_running_loop()
    draft = await loop.run_in_executor(None, get_db().get_draft, payload.draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在或已过期，请重新生成")

    try:
        excel_service = ExcelService(settings.export_path)
        sku = str(draft["sku"])
        upload_path = Path(str(draft["upload_path"]))
        upload_files_raw = draft.get("upload_files", {})
        upload_files = {
            name: Path(path)
            for name, path in upload_files_raw.items()  # type: ignore[union-attr]
        }
        web_ref_files_raw = draft.get("web_ref_files", {})
        web_ref_files = {
            name: Path(path)
            for name, path in web_ref_files_raw.items()  # type: ignore[union-attr]
        }
        image_requirements = draft["image_requirements"]

        requirements = [ImageRequirement(**item) for item in image_requirements]  # type: ignore[arg-type]
        listing_data = draft.get("listing_data") or {}
        export_listing = (
            ListingData(**listing_data)
            if listing_data
            else ListingData(
                sku=sku,
                title=sku,
                bullet_points=[],
                description="",
                keywords=[],
                oe_numbers=[],
            )
        )
        export_analysis = ProductAnalysis(**(draft.get("product_analysis") or {}))
        export_copy = CopyBlock(**(draft.get("copy_block") or {}))
        AiService.sanitize_compliance_output(
            export_analysis, export_copy, requirements, export_listing
        )
        excel_file = excel_service.export_sop(
            sku,
            requirements,
            main_image_path=upload_path,
            upload_files=upload_files,
            web_ref_files=web_ref_files,
        )
        return {"excel_file": f"/api/files/{excel_file.name}"}
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"导出 Excel 失败: {exc}\n{tb}")
        raise HTTPException(
            status_code=500,
            detail=f"导出失败: {str(exc)[:300]}",
        ) from exc


@app.post("/api/sop/export-premium")
async def export_sop_premium(payload: SopExportRequest) -> dict[str, str]:
    """生成并导出高级A+图 Excel（9列模板，文案顺序：车型/OE → 产品特点）。"""
    loop = asyncio.get_running_loop()
    draft = await loop.run_in_executor(None, get_db().get_draft, payload.draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在或已过期，请重新生成")

    try:
        sku = str(draft["sku"])
        upload_path = Path(str(draft["upload_path"]))
        upload_files_raw = draft.get("upload_files", {})
        upload_files = {
            name: Path(path)
            for name, path in upload_files_raw.items()
        }
        web_ref_files_raw = draft.get("web_ref_files", {})
        web_ref_files = {
            name: Path(path)
            for name, path in web_ref_files_raw.items()
        }

        # 优先使用已预生成的高级A+内容，实现秒级导出
        premium_image_requirements: list[ImageRequirement] | None = None
        premium_reqs_raw = draft.get("premium_image_requirements", [])
        if premium_reqs_raw:
            premium_image_requirements = [ImageRequirement(**item) for item in premium_reqs_raw]  # type: ignore[arg-type]
            listing_data = draft.get("listing_data") or {}
            export_listing = (
                ListingData(**listing_data)
                if listing_data
                else ListingData(sku=sku, title=sku, bullet_points=[], description="", keywords=[], oe_numbers=[])
            )
            AiService.sanitize_compliance_output(
                ProductAnalysis(),
                CopyBlock(headline="", subheadline="", body="", keywords=[]),
                premium_image_requirements,
                export_listing,
            )
            logger.info(f"使用预生成高级A+内容导出 SKU={sku}")

        # 没有缓存则实时生成（兼容旧草稿）
        if not premium_image_requirements:
            listing_data = draft.get("listing_data") or {}
            listing = ListingData(**listing_data) if listing_data else ListingData(
                sku=sku, title=sku, bullet_points=[], description="", keywords=[], oe_numbers=[]
            )

            img_reqs_raw = draft.get("image_requirements", [])
            detail_urls: list[str] = []
            scene_urls: list[str] = []
            main_image_url = ""
            for ir in img_reqs_raw:
                if ir.get("index") == 1:
                    main_image_url = ir.get("reference_image", "")
                di = ir.get("detail_image", "")
                si = ir.get("scene_image", "")
                if di and di not in detail_urls:
                    detail_urls.append(di)
                if si and si not in scene_urls:
                    scene_urls.append(si)
            detail_urls = list(dict.fromkeys(detail_urls))
            scene_urls = list(dict.fromkeys(scene_urls))
            main_image_url = main_image_url or ""
            has_refs = bool(detail_urls or scene_urls)

            standard_copy_raw = draft.get("copy_block") or {}
            standard_copy = CopyBlock(
                headline=str(standard_copy_raw.get("headline", "")).strip(),
                subheadline=str(standard_copy_raw.get("subheadline", "")).strip(),
                body=str(standard_copy_raw.get("body", "")).strip(),
                keywords=standard_copy_raw.get("keywords", []),
            )
            analysis_raw = draft.get("product_analysis") or {}
            standard_analysis = ProductAnalysis(
                function=str(analysis_raw.get("function", "")).strip(),
                installation=str(analysis_raw.get("installation", "")).strip(),
                inspection=str(analysis_raw.get("inspection", "")).strip(),
                maintenance=str(analysis_raw.get("maintenance", "")).strip(),
                compatibility=str(analysis_raw.get("compatibility", "")).strip(),
                oe_numbers=str(analysis_raw.get("oe_numbers", "")).strip(),
                quality=str(analysis_raw.get("quality", "")).strip(),
            )

            ai_service = AiService(settings)
            draft_link_flags = draft.get("scene_link_sources") or []
            _, _, premium_image_requirements, _ = (
                await ai_service.generate_premium_copy_and_requirements(
                    listing=listing,
                    main_image=main_image_url,
                    detail_reference_urls=detail_urls,
                    scene_reference_urls=scene_urls,
                    has_operator_references=has_refs,
                    sku=sku,
                    main_image_path=upload_path,
                    standard_copy=standard_copy,
                    standard_analysis=standard_analysis,
                    scene_link_sources=draft_link_flags if isinstance(draft_link_flags, list) else None,
                )
            )
            # ── 追加局部图行到高级A+（回退生成时同步追加）──
            dtl_urls_backup = draft.get("detail_local_urls", [])
            if dtl_urls_backup:
                backup_count = len(dtl_urls_backup)
                if backup_count >= 4:
                    premium_design_request_backup = (
                        "将4张产品局部细节图按2×2网格拼接为一张完整的高级A+ PRODUCT DETAILS图："
                        "顶部放置大写标题'PRODUCT DETAILS'；4张局部图均匀分布，等比例缩放并居中裁剪填满网格，"
                        "统一圆角边框和间距；背景使用深色或品牌色渐变，突出产品细节与金属/塑料质感。"
                    )
                elif backup_count == 3:
                    premium_design_request_backup = (
                        "将3张产品局部细节图横向三等分拼接为一张完整的高级A+ PRODUCT DETAILS图："
                        "顶部放置大写标题'PRODUCT DETAILS'；3张图等比例缩放居中裁剪，统一间距与圆角边框；背景使用深色或品牌色。"
                    )
                elif backup_count == 2:
                    premium_design_request_backup = (
                        "将2张产品局部细节图左右并排拼接为一张完整的高级A+ PRODUCT DETAILS图："
                        "顶部放置大写标题'PRODUCT DETAILS'；2张图各占一半宽度，等比例缩放居中裁剪，统一间距；背景使用深色或品牌色。"
                    )
                else:
                    premium_design_request_backup = (
                        "将1张产品局部细节图作为高级A+ PRODUCT DETAILS图的主体："
                        "图片居中放大展示，顶部放置大写标题'PRODUCT DETAILS'；背景使用深色或品牌色，突出产品细节。"
                    )
                # 局部图行放在倒数第二（品牌保障之前），若列表不足2项则追加到末尾
                premium_image_requirements = list(premium_image_requirements)
                premium_product_details_backup = ImageRequirement(
                    index=len(premium_image_requirements) + 1,
                    theme="PRODUCT DETAILS",
                    size=settings.sop_premium_image_size,
                    copy_text="",
                    design_request=premium_design_request_backup,
                    reference_image=dtl_urls_backup[0],
                    reference_images=list(dtl_urls_backup),
                    reference_source="detail_local",
                )
                if len(premium_image_requirements) >= 2:
                    premium_image_requirements.insert(-1, premium_product_details_backup)
                else:
                    premium_image_requirements.append(premium_product_details_backup)
                for i, req in enumerate(premium_image_requirements, 1):
                    req.index = i
            logger.info(f"实时生成高级A+内容并导出 SKU={sku}")

        excel_service = ExcelService(settings.export_path)
        excel_file = excel_service.export_sop_premium(
            sku,
            premium_image_requirements,
            main_image_path=upload_path,
            upload_files=upload_files,
            web_ref_files=web_ref_files,
        )
        return {"excel_file": f"/api/files/{excel_file.name}"}
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"导出高级A+ Excel 失败: {exc}\n{tb}")
        raise HTTPException(
            status_code=500,
            detail=f"导出失败: {str(exc)[:300]}",
        ) from exc


def _preload_nas_thumbnails(paths: list[str], max_images: int | None = None, workers: int | None = None):
    """后台并行预下载 NAS 缩略图，避免前端一张张等待。不影响主流程。"""
    if not _nas_ready():
        return
    limit = max_images or settings.nas_thumb_preload_max
    worker_count = max(1, workers or settings.nas_thumb_preload_workers)
    service = _make_nas_service()
    try:
        if not service.ensure_login():
            return

        def _fetch_one(path: str) -> bool:
            try:
                return service.download_thumbnail(path) is not None
            except Exception as exc:
                logger.debug(f"预缓存缩略图跳过 {path}: {exc}")
                return False

        targets = paths[:limit]
        count = 0
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            for ok in pool.map(_fetch_one, targets):
                if ok:
                    count += 1
        if count:
            logger.info(f"NAS 缩略图预缓存完成: {count}/{len(targets)} 张")
    except Exception as exc:
        logger.warning(f"NAS 后台预缓存任务异常: {exc}")
    finally:
        service.close()


@app.get("/api/nas/search")
async def nas_search(background_tasks: BackgroundTasks, sku: str = "") -> dict[str, object]:
    """按 MSKU 搜索 NAS 上的图片"""
    normalized_sku = sku.strip()
    if not normalized_sku:
        raise HTTPException(status_code=400, detail="sku 不能为空")
    if not _nas_ready():
        raise HTTPException(status_code=503, detail="NAS 未配置或未启用")

    service = _make_nas_service()
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, service.search_by_sku, normalized_sku)
        paths = [img.path for m in result.matches for img in m.images]
        background_tasks.add_task(_preload_nas_thumbnails, paths)

        return {
            "msku": result.msku,
            "match_count": len(result.matches),
            "total_images": result.total_images,
            "search_time_ms": round(result.search_time_ms, 0),
            "matches": [
                {
                    "sku_code": m.sku_code,
                    "folder_path": m.folder_path,
                    "month_dir": m.month_dir,
                    "match_score": m.match_score,
                    "matched_patterns": m.matched_patterns,
                    "has_raw": m.has_raw,
                    "images": [
                        {
                            "name": img.name,
                            "path": img.path,
                            "size": img.size,
                            "url": _nas_media_url("image", img.path),
                            "thumb": _nas_media_url("thumb", img.path),
                            "is_white_bg": NasImageService._is_white_bg_image(img.name),
                            "is_likely_main": NasImageService._is_likely_main_image(
                                img.name, img.folder_path or m.folder_path
                            ),
                            "is_raw_file": NasImageService._is_raw_file(img.name),
                        }
                        for img in m.images
                    ],
                }
                for m in result.matches
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"NAS 搜索失败: {exc}") from exc
    finally:
        service.close()


THUMB_SIZE = (200, 200)


def _get_or_create_thumbnail(image_path):
    """生成缩略图并缓存到磁盘"""
    thumb_dir = settings.nas_cache_path / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / ("thumb_" + image_path.name)
    if thumb_path.suffix.lower() not in (".jpg", ".jpeg"):
        thumb_path = thumb_path.with_suffix(".jpg")
    if thumb_path.exists() and thumb_path.stat().st_size > 1024:
        return thumb_path
    try:
        from PIL import Image
        img = Image.open(image_path)
        img.thumbnail(THUMB_SIZE, Image.LANCZOS)
        img.save(thumb_path, "JPEG", quality=60)
        return thumb_path
    except Exception:
        return image_path


@app.get("/api/nas/thumb")
async def nas_thumb_proxy(p: str = Query(default="", description="NAS image path for thumbnail")):
    """返回缩略图，优先 NAS 原生的缩略图 API，大大减少传输量，并长期缓存"""
    if not p:
        raise HTTPException(status_code=400, detail="缺少图片路径参数 p")
    decoded_p = _assert_nas_media_path(p)
    if not _nas_ready():
        raise HTTPException(status_code=503, detail="NAS 未配置或未启用")

    # 磁盘缓存检查：已有完整缩略图则直接返回
    thumb_dir = settings.nas_cache_path / "thumbs"
    cache_name = "thumb_" + decoded_p.replace("/", "_").lstrip("_")
    cached_thumb = thumb_dir / cache_name
    if cached_thumb.suffix.lower() not in (".jpg", ".jpeg"):
        cached_thumb = cached_thumb.with_suffix(".jpg")
    if cached_thumb.exists() and cached_thumb.stat().st_size > 1024:
        return FileResponse(
            cached_thumb,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    # 第二优先级：已有下载的原图，本地生成缩略图
    full_cache_name = decoded_p.replace("/", "_").lstrip("_")
    cached_full = settings.nas_cache_path / full_cache_name
    if cached_full.exists() and cached_full.stat().st_size > 0:
        thumb = _get_or_create_thumbnail(cached_full)
        return FileResponse(
            thumb,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    # 需要从 NAS 获取：优先尝试 Thumb API，失败则下载原图
    service = _make_nas_service()
    try:
        thumb_path = service.download_thumbnail(decoded_p)
        if thumb_path:
            return FileResponse(
                thumb_path,
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )
        raise HTTPException(status_code=404, detail="图片不存在或下载失败")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"缩略图生成失败: {exc}") from exc
    finally:
        service.close()


def _guess_media_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


@app.get("/api/nas/image")
async def nas_image_proxy(p: str = Query(default="", description="NAS image path")) -> FileResponse:
    """代理访问 NAS 图片（下载到本地缓存后返回）"""
    if not p:
        raise HTTPException(status_code=400, detail="缺少图片路径参数 p")
    decoded_p = _assert_nas_media_path(p)
    if not _nas_ready():
        raise HTTPException(status_code=503, detail="NAS 未配置或未启用")

    cache_name = decoded_p.replace("/", "_").lstrip("_")
    cached = settings.nas_cache_path / cache_name
    if cached.exists() and cached.stat().st_size > 0:
        media_type = _guess_media_type(cached)
        return FileResponse(cached, media_type=media_type)

    service = _make_nas_service()
    try:
        local_path = service.download_image(decoded_p)
        if local_path:
            media_type = _guess_media_type(local_path)
            return FileResponse(local_path, media_type=media_type)
        raise HTTPException(status_code=404, detail="图片不存在或下载失败")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"NAS 下载失败: {exc}") from exc
    finally:
        service.close()

@app.get("/api/files/{filename}")
async def download_file(filename: str) -> FileResponse:
    file_path = _safe_path_in_dir(settings.export_path, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(file_path, filename=file_path.name, media_type="application/octet-stream")


@app.get("/api/web-refs/{filename}")
async def get_web_ref(filename: str) -> FileResponse:
    file_path = _safe_path_in_dir(settings.web_ref_path, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="参考图不存在")
    return FileResponse(file_path)


@app.get("/api/uploads/{filename}")
async def get_upload(filename: str) -> FileResponse:
    file_path = _safe_path_in_dir(settings.upload_path, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(file_path)


# ── AI 车型搜索：根据 MSKU 分析产品关联的热门车型 ──


@app.post("/api/ai/vehicle-search")
async def ai_vehicle_search(
    sku: str = Form(...),
    sid: int | None = Form(None),
    source_mode: str = Form(default="sku"),
    listing_data_json: str = Form(default=""),
) -> dict[str, object]:
    """根据 MSKU / eBay 竞品信息，通过 AI 深度分析并输出热门适配车型/设备型号。"""
    normalized_sku = sku.strip()
    if not normalized_sku:
        raise HTTPException(status_code=400, detail="SKU 不能为空")
    if not settings.active_ai_api_key:
        raise HTTPException(status_code=503, detail="AI 服务未配置")

    mode = (source_mode or "sku").strip().lower()
    ai_service = AiService(settings)
    loop = asyncio.get_running_loop()

    if mode == "ebay":
        if not listing_data_json.strip():
            raise HTTPException(status_code=400, detail="请先获取 eBay 产品信息")
        try:
            listing = ListingData.model_validate(_json.loads(listing_data_json))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"listing 数据无效: {exc}") from exc
        listing.sku = normalized_sku
        cache_key = f"ebay:{normalized_sku}:{_listing_cache_version(listing)}"
        listing_version = _listing_cache_version(listing)
    else:
        store_sid = _parse_store_sid(sid)
        if store_sid is None:
            raise HTTPException(status_code=400, detail="请选择亚马逊店铺")
        if settings.lingxing_use_mock:
            raise HTTPException(status_code=400, detail="当前为 Mock 模式，请配置真实领星参数")

        lingxing_service = LingxingService(settings)
        try:
            listing = await lingxing_service.get_listing_by_sku(normalized_sku, sid=store_sid)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"领星查询失败: {getattr(exc, 'message', str(exc))}",
            ) from exc
        cache_key = _profile_cache_key(store_sid, normalized_sku)
        listing_version = _listing_cache_version(listing)

    cache_max_age = max(1, settings.ai_profile_cache_ttl_hours) * 3600
    product_info = await loop.run_in_executor(
        None,
        get_db().get_ai_profile,
        cache_key,
        listing_version,
        cache_max_age,
    )
    try:
        if not product_info:
            product_info = await ai_service._analyze_product_deeply(listing, normalized_sku)
            await loop.run_in_executor(
                None,
                get_db().save_ai_profile,
                cache_key,
                listing_version,
                product_info,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"AI 分析失败: {getattr(exc, 'message', str(exc))}",
        ) from exc

    vehicles = await ai_service.recommend_popular_vehicles(listing, product_info)
    product_name = product_info.get("product_name", "")
    product_category = product_info.get("product_category", "")
    product_type = product_info.get("product_type", "")
    core_features = product_info.get("core_features", [])
    oe_numbers = listing.oe_numbers[:12] if listing.oe_numbers else []
    listing_title = listing.title or ""

    return {
        "sku": normalized_sku,
        "source_mode": mode,
        "product_name": product_name,
        "product_category": product_category,
        "product_type": product_type,
        "core_features": core_features,
        "compatible_vehicles": vehicles,
        "vehicle_count": len(vehicles),
        "oe_numbers": oe_numbers,
        "listing_title": listing_title,
    }


# AI 图片搜索：为场景图/物品图提供 5 张候选图片供运营选择


class AiImageSearchRequest(_PydanticBaseModel):
    query: str = ""              # 兼容旧版简单搜索词
    source_type: str = "mix"     # "mix"（场景物品图统一搜索）
    refresh: bool = False        # True = 换一批（重新生成搜索角度）
    product_context: dict[str, str] = {}  # {title, function, compatibility, quality} - AI 多角度分析用


# 场景物品图后缀（混合场景+物品引导词）
_MIX_SUFFIXES = [
    "installation scene",
    "real environment context",
    "in use application",
    "mounted setup",
    "product photo",
    "closeup detail",
    "replacement part",
    "component detail",
    "isolated view",
    "real world usage",
    "workshop repair",
    "engine compartment",
    "product detail",
    "spare part",
]

# 上一次搜索的角度索引（避免连续两次相同）
# _last_search_angle 已弃用（搜索缓存已由 _search_cache 管理）

# 搜索结果缓存（TTL 5 分钟）
_search_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
_SEARCH_CACHE_TTL = 300  # 秒


# 角度标签映射（与 AI 生成的 4 个查询顺序对应）
_ANGLE_LABELS: list[str] = ["热门车型", "安装场景", "品质细节", "加工场景"]


@app.post("/api/ai-search-images")
async def ai_search_images(payload: AiImageSearchRequest) -> dict[str, object]:
    """搜索 5 张场景物品图，下载供运营预览选择。

    新版：前端传入 product_context（产品分析数据），后端 AI 分析产品类型后
    生成 4 个不同角度的搜索词（物品/场景关联、安装/使用、品质细节、加工/行业场景），
    分别搜索后合并去重返回，每张图带角度标签。

    旧版兼容：product_context 为空时使用 query 单搜索词模式。
    refresh=True 时重新生成 AI 搜索词以获得不同结果。
    """

    source_type = payload.source_type
    if source_type not in ("mix", "scene", "item"):
        raise HTTPException(status_code=400, detail="source_type 必须是 mix、scene 或 item")
    if not settings.web_search_enabled:
        raise HTTPException(
            status_code=400,
            detail="场景搜图未开启，请本地上传或从 NAS 选",
        )

    refresh = payload.refresh
    product_ctx = payload.product_context or {}
    raw_query = (payload.query or "").strip()

    # ── 缓存检查（refresh 时跳过缓存）──
    ctx_key = ""
    if product_ctx:
        ctx_key = f"{product_ctx.get('title','')[:30]}|{product_ctx.get('function','')[:30]}"
    cache_key = f"{source_type}:{ctx_key}:{'refresh' if refresh else 'first'}"
    now = time.time()
    if not refresh and cache_key in _search_cache:
        cached_at, cached_results = _search_cache[cache_key]
        if now - cached_at < _SEARCH_CACHE_TTL:
            logger.info(f"AI 图片搜索命中缓存({source_type}): {len(cached_results)} 张")
            return {"images": cached_results, "cached": True, "query": ""}

    web_ref_dir = settings.web_ref_path
    web_ref_dir.mkdir(parents=True, exist_ok=True)

    # ── 搜索词生成 ──
    search_queries: list[str] = []
    use_multi_angle = False

    if product_ctx and any(
        product_ctx.get(k, "") and product_ctx[k] != "-" and len(product_ctx[k]) > 3
        for k in ("title", "function", "compatibility", "quality")
    ):
        # 新版：先从产品信息提取确定性搜索词，再与 AI 查询合并
        deterministic = build_deterministic_scene_queries(product_ctx)
        logger.info(f"确定性多角度查询: {[q[:50] for q in deterministic]}")
        ai_queries: list[str] | None = None
        try:
            ai_queries = await generate_multi_angle_queries(
                product_context=product_ctx,
                api_base=settings.active_ai_api_base,
                api_key=settings.active_ai_api_key,
                model=settings.active_ai_model,
                timeout=8,
            )
        except Exception as exc:
            logger.debug(f"AI 多角度查询异常，使用确定性模板: {exc}")
        search_queries = merge_scene_queries(deterministic, ai_queries)
        use_multi_angle = True
        logger.info(f"最终多角度查询({len(search_queries)}): {[q[:50] for q in search_queries]}")

    if not search_queries:
        # 旧版兼容 / 降级：使用 query + suffix
        if not raw_query:
            raise HTTPException(status_code=400, detail="搜索关键词不能为空")
        refined = await refine_query_with_ai(
            query=raw_query,
            source_type=source_type,
            api_base=settings.active_ai_api_base,
            api_key=settings.active_ai_api_key,
            model=settings.active_ai_model,
            timeout=5,
        )
        refresh_offset = random.randint(1, len(_MIX_SUFFIXES) - 1) if refresh else 0
        search_queries = [f"{refined} {_MIX_SUFFIXES[refresh_offset]}"]

    # ── 多查询搜索：4 角度各至少 1 张，共 5 张 ──
    total_target = 5
    all_saved: dict[str, Path] = {}
    image_labels: dict[str, str] = {}  # filename → 角度标签
    prefix_base = f"ai_mix_{uuid4().hex[:4]}_"
    angle_labels = _ANGLE_LABELS if use_multi_angle and len(search_queries) >= 4 else []

    service = WebImageSearchService(
        timeout=settings.web_search_timeout,
        engine=settings.web_search_engine,
        proxy=settings.web_search_proxy,
        max_image_size_mb=settings.web_search_max_image_size_mb,
    )

    try:
        # 第一轮：每个角度搜 1 张，保证覆盖 4 个角度
        for i, q in enumerate(search_queries):
            if len(all_saved) >= total_target:
                break
            prefix = f"{prefix_base}q{i}_r1_"
            scene_type = _SCENE_TYPES[i] if i < len(_SCENE_TYPES) else ""
            saved = await service.download_images(
                query=q, save_dir=web_ref_dir,
                max_results=1, prefix=prefix, fast_mode=True,
                scene_type=scene_type,
            )
            for url, path in saved.items():
                if len(all_saved) >= total_target:
                    break
                all_saved[url] = path
                if i < len(angle_labels):
                    image_labels[path.name] = angle_labels[i]
            logger.debug(f"[R1] '{q[:40]}' → {len(saved)} 张（累计 {len(all_saved)}）")

        # 第二轮：补充剩余缺额，从角度 0 开始搜
        if len(all_saved) < total_target:
            remaining = total_target - len(all_saved)
            for i, q in enumerate(search_queries):
                if remaining <= 0:
                    break
                prefix = f"{prefix_base}q{i}_r2_"
                scene_type = _SCENE_TYPES[i] if i < len(_SCENE_TYPES) else ""
                saved = await service.download_images(
                    query=q, save_dir=web_ref_dir,
                    max_results=min(2, remaining), prefix=prefix, fast_mode=True,
                    scene_type=scene_type,
                )
                for url, path in saved.items():
                    if remaining <= 0:
                        break
                    all_saved[url] = path
                    remaining -= 1
                    if i < len(angle_labels):
                        image_labels[path.name] = angle_labels[i]
                logger.debug(f"[R2] '{q[:40]}' → {len(saved)} 张（累计 {len(all_saved)}）")
    except Exception as exc:
        logger.warning(f"AI 图片搜索网络异常: {exc}")
    finally:
        await service.close()

    results: list[dict[str, str]] = []
    for filename in all_saved.values():
        name = filename.name
        results.append({
            "filename": name,
            "url": f"/api/web-refs/{name}",
            "thumb_url": f"/api/web-refs/{name}",
            "label": image_labels.get(name, ""),
        })

    # ── 缓存结果 ──
    if results:
        _search_cache[cache_key] = (now, results)

    logger.info(f"AI 图片搜索({source_type}) {len(search_queries)} 查询 → {len(results)} 张, labels: {set(image_labels.values())}")
    return {
        "query": search_queries[0] if search_queries else "",
        "source_type": source_type,
        "images": results,
        "count": len(results),
        "refreshed": refresh,
        "all_queries": search_queries,
        "angle_labels": angle_labels,
    }


def _build_fallback_query(ctx: dict[str, str]) -> str:
    """AI 多角度生成不可用时，用产品上下文拼一个合理的搜索词。"""
    parts = []
    title = ctx.get("title", "")
    func = ctx.get("function", "")
    compat = ctx.get("compatibility", "")
    if title and title != "-" and title != "...":
        parts.append(title.split(" ")[:4])
        parts = [w for s in parts for w in (s if isinstance(s, list) else [s])]
    if func and func != "-" and len(func) > 3:
        parts.append(func[:60])
    if compat and compat != "-" and len(compat) > 3:
        parts.append(compat[:60])
    q = " ".join(parts[:6]).strip()
    return q if q else ctx.get("sku", "")


# ── eBay 竞品链接解析 ──

@app.get("/api/ebay/status")
async def ebay_status() -> dict:
    service = EbayListingService(settings)
    return {"configured": service.is_configured()}


@app.post("/api/ebay/parse-url")
async def ebay_parse_url(payload: EbayParseUrlRequest) -> dict:
    service = EbayListingService(settings)
    if not service.is_configured():
        raise HTTPException(
            status_code=400,
            detail="eBay API 未配置，请在 .env 中设置 EBAY_CLIENT_ID 和 EBAY_CLIENT_SECRET",
        )
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            service.parse_listing_from_url,
            payload.url,
            payload.site,
        )
    except ValueError as exc:
        logger.warning("eBay parse-url rejected input=%r: %s", (payload.url or "")[:200], exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("eBay parse-url failed")
        raise HTTPException(status_code=500, detail=f"eBay 解析失败: {exc}") from exc
    return result


# ── 链接获取：从 URL 下载图片供运营使用 ──

@app.post("/api/download-from-url")
async def download_from_url(payload: dict[str, str]) -> dict:
    """从指定的图片 URL 下载图片到服务器，返回可引用的本地 URL。

    运营人员粘贴图片链接，后端下载后返回 /api/web-refs/xxx.jpg，
    前端将其加入已选图片列表。
    """
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="图片 URL 不能为空")

    referer = (payload.get("referer") or "").strip()
    if not referer and "ebayimg.com" in url.lower():
        referer = "https://www.ebay.com/"

    # 简单校验：必须是 http/https 开头
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="图片 URL 必须以 http:// 或 https:// 开头")

    web_ref_dir = settings.web_ref_path
    web_ref_dir.mkdir(parents=True, exist_ok=True)

    # 常见图片扩展名映射
    _EXT_MAP = {
        "image/jpeg": ".jpg", "image/jpg": ".jpg",
        "image/png": ".png", "image/webp": ".webp",
        "image/gif": ".gif", "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }

    # 模拟浏览器请求头，绕过防盗链
    _DL_HEADERS = {
        "User-Agent": _DEFAULT_USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer or "https://www.amazon.com/",
    }

    try:
        async with _httpx_for_dl.AsyncClient(
            timeout=_httpx_for_dl.Timeout(30), follow_redirects=False,
            headers=_DL_HEADERS,
        ) as client:
            resp = await _safe_external_get(client, url)
            if not (200 <= resp.status_code < 300):
                hint_map = {403: "被源站拒绝（防盗链或地区限制）", 404: "图片链接不存在", 429: "请求太频繁，源站限流"}
                hint = hint_map.get(resp.status_code, "")
                detail = f"下载失败: HTTP {resp.status_code}{' - ' + hint if hint else ''}"
                logger.warning(f"链接下载 {resp.status_code}: {url[:100]}")
                raise HTTPException(status_code=400, detail=detail)

            content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            # 过滤非图片
            if not content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail=f"目标不是图片（Content-Type: {content_type}）")

            max_image_bytes = max(1, settings.web_search_max_image_size_mb) * 1024 * 1024
            if len(resp.content) > max_image_bytes:
                raise HTTPException(status_code=413, detail="远程图片超过允许大小")

            ext = _EXT_MAP.get(content_type, ".jpg")
            filename = f"link_{uuid4().hex[:8]}{ext}"
            filepath = web_ref_dir / filename

            filepath.write_bytes(resp.content)

            # 验证文件确实可识别为图片
            from PIL import Image as _PILImage
            try:
                _PILImage.open(filepath).verify()
            except Exception:
                filepath.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="下载的内容不是有效图片")

            logger.info(f"链接下载: {url[:80]} → {filename} ({filepath.stat().st_size} bytes)")

        return {
            "filename": filename,
            "url": f"/api/web-refs/{filename}",
            "size": filepath.stat().st_size,
        }
    except HTTPException:
        raise
    except _httpx_for_dl.ConnectError as exc:
        logger.warning(f"链接下载网络不可达: {url[:100]} → {exc}")
        raise HTTPException(status_code=502, detail=f"下载失败: 目标服务器无法连接")
    except _httpx_for_dl.TimeoutException as exc:
        logger.warning(f"链接下载超时: {url[:100]} → {exc}")
        raise HTTPException(status_code=504, detail=f"下载失败: 目标服务器超时")
    except Exception as exc:
        logger.warning(f"链接下载失败: {url[:100]} → {exc}")
        raise HTTPException(status_code=400, detail=f"下载失败: {exc}")


# ── 网页图片提取：从网页中提取所有图片链接供运营挑选 ──

def _extract_ld_images(obj, add_callback):
    """递归从 JSON-LD 对象中提取所有图片 URL"""
    if isinstance(obj, str):
        if obj.startswith("http") and any(ext in obj.lower() for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
            add_callback(obj)
        elif obj.startswith("http") and "/image" in obj.lower():
            add_callback(obj)
    elif isinstance(obj, dict):
        for key in ("image", "thumbnail", "thumbnailUrl", "url", "contentUrl"):
            if key in obj and isinstance(obj[key], (str, list)):
                val = obj[key]
                if isinstance(val, str):
                    _extract_ld_images(val, add_callback)
                elif isinstance(val, list):
                    for v in val:
                        _extract_ld_images(v, add_callback)
        # 递归遍历所有值
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _extract_ld_images(v, add_callback)
    elif isinstance(obj, list):
        for v in obj:
            _extract_ld_images(v, add_callback)


@app.post("/api/extract-web-images")
async def extract_web_images(payload: dict[str, str]) -> dict:
    """抓取网页 HTML，提取所有 img 标签的图片链接，去重后返回。

    前端展示缩略图列表，运营人员挑选后逐个下载。
    """
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="网页 URL 不能为空")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="网页 URL 必须以 http:// 或 https:// 开头")

    _WEB_HEADERS = {
        "User-Agent": _DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    try:
        async with _httpx_for_dl.AsyncClient(
            timeout=_httpx_for_dl.Timeout(30), follow_redirects=False,
            headers=_WEB_HEADERS,
        ) as client:
            resp = await _safe_external_get(client, url)
            if not (200 <= resp.status_code < 300):
                raise HTTPException(status_code=400, detail=f"网页访问失败: HTTP {resp.status_code}")

            if len(resp.content) > 5 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="网页内容超过 5MB，已拒绝解析")
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            base_url = url
            base_tag = soup.find("base", href=True)
            if base_tag:
                base_url = urljoin(base_url, base_tag["href"])

            images: list[dict] = []
            seen: set[str] = set()
            _SKIP_EXTS = (".css", ".js", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".eot")

            def _add_image(src: str, alt: str = "", width: str = "", height: str = ""):
                full_url = urljoin(base_url, src)
                if full_url in seen:
                    return
                seen.add(full_url)
                if full_url.startswith("data:") or full_url.startswith("javascript:"):
                    return
                parsed = urlparse(full_url)
                path_lower = parsed.path.lower()
                if path_lower.endswith(_SKIP_EXTS):
                    return
                # 过滤常见的 tracking/site-logo 等
                low = full_url.lower()
                for noise in ("fls-na.amazon.com/1/oc-csi", "pixel.", "tracking.", "logo.", "icon.", "avatar."):
                    if noise in low:
                        return
                images.append({"url": full_url, "alt": alt, "width": width, "height": height})

            # 1. 从 img 标签提取
            for img in soup.find_all("img"):
                src = (img.get("src") or img.get("data-src") or img.get("data-original") or img.get("data-srcset") or "").strip()
                # srcset 只取第一个
                if src and "," in src:
                    src = src.split(",")[0].strip().split(" ")[0].strip()
                if not src:
                    continue
                _add_image(src, (img.get("alt") or "").strip(), img.get("width") or "", img.get("height") or "")

            # 2. 用正则从 HTML 中提取所有 http/https 图片链接（防止 JS 渲染漏掉）
            all_urls = re.findall(r'(?:src|href|content)\s*=\s*["\'](https?://[^"\']+\.(?:jpe?g|png|webp|gif|bmp|tiff?)(?:\?[^"\']*)?)["\']', html, re.IGNORECASE)
            for u in all_urls:
                _add_image(u)

            # 3. 从 JSON-LD / schema.org Product 提取 image 字段
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    ld = _json.loads(script.string or "")
                except Exception:
                    continue
                _extract_ld_images(ld, _add_image)

            # 4. 正则兜底：从 HTML 中找所有图片 URL（不限标签，后面跟着 ? 参数也可以）
            if len(images) < 3:
                loose_re = re.findall(r'https?://[^"\'<>\s]+\.(?:jpe?g|png|webp|gif|bmp)(?:\?[^"\'<>\s]*)?', html, re.IGNORECASE)
                for u in loose_re:
                    _add_image(u)

            # 5. Playwright 回退：静态抓取不够时用无头浏览器渲染 JS 页面
            if len(images) < 3:
                try:
                    from playwright.async_api import async_playwright
                    async with async_playwright() as pw:
                        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
                        page = await browser.new_page()
                        await page.goto(url, wait_until="networkidle", timeout=20000)
                        pw_html = await page.content()
                        await browser.close()

                    pw_soup = BeautifulSoup(pw_html, "html.parser")
                    for img in pw_soup.find_all("img"):
                        src = (img.get("src") or img.get("data-src") or img.get("data-original") or "").strip()
                        if src and "," in src:
                            src = src.split(",")[0].strip().split(" ")[0].strip()
                        if src:
                            _add_image(src, (img.get("alt") or "").strip())
                    # 再用正则搜一遍渲染后的 HTML
                    pw_urls = re.findall(r'https?://[^"\'<>\s]+\.(?:jpe?g|png|webp|gif|bmp)(?:\?[^"\'<>\s]*)?', pw_html, re.IGNORECASE)
                    for u in pw_urls:
                        _add_image(u)
                    # JSON-LD 也可能在渲染后出现
                    for script in pw_soup.find_all("script", type="application/ld+json"):
                        try:
                            ld = _json.loads(script.string or "")
                        except Exception:
                            continue
                        _extract_ld_images(ld, _add_image)

                    logger.info(f"Playwright 回退提取 +{len(images)} 张")
                except Exception as pw_exc:
                    logger.info(f"Playwright 回退失败（不影响主流程）: {pw_exc}")

            logger.info(f"网页提取: {url[:80]} → {len(images)} 张候选图片")

        return {
            "page_url": url,
            "images": images,
            "count": len(images),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"网页提取失败: {url[:100]} → {exc}")
        raise HTTPException(status_code=400, detail=f"提取失败: {exc}")
