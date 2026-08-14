"""任务调度层：紫鸟浏览器启动 → 连接 → 读取 SKU → 循环上传。

通过回调把进度和日志推送给 GUI。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
from datetime import datetime
from typing import Any, Callable

from loguru import logger

from .amazon_bot import AmazonBot
from .excel_reader import read_skus
from .image_loader import get_sku_images
from .ziniao_client import ZiniaoClient

# 进度/日志回调类型
LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int, str], None]  # done_sku, total_sku, msg


def _exception_text(exc: BaseException) -> str:
    detail = str(exc).strip()
    return detail or f"{type(exc).__name__}: {exc!r}"


class UploadApp:
    """主调度器。"""

    def __init__(
        self,
        cfg: dict[str, Any],
        completed_loader: Callable[[], set[str]] | None = None,
        completed_marker: Callable[[str], None] | None = None,
    ):
        self.cfg = cfg
        self.bot = AmazonBot(cfg)
        self.ziniao = ZiniaoClient(cfg.get("ziniao", {}) or {})
        self._stop_flag = False
        self._log_cb: LogCallback | None = None
        self._prog_cb: ProgressCallback | None = None
        self._shop_id: str = ""  # 当前使用的紫鸟店铺ID
        self._browser_started = False  # 紫鸟店铺是否已启动
        self._completed_loader = completed_loader
        self._completed_marker = completed_marker

    def set_callbacks(self, log_cb: LogCallback | None, prog_cb: ProgressCallback | None) -> None:
        self._log_cb = log_cb
        self._prog_cb = prog_cb

    def set_shop_id(self, shop_id: str) -> None:
        """设置要使用的紫鸟店铺ID（由 GUI 传入）。"""
        self._shop_id = shop_id

    def stop(self) -> None:
        """请求停止（优雅结束：完成当前步骤后退出）。"""
        self._stop_flag = True
        self._log("收到停止请求，将在当前步骤完成后退出")

    def _log(self, msg: str) -> None:
        logger.info(msg)
        if self._log_cb:
            self._log_cb(msg)

    def _prog(self, d_sku: int, t_sku: int, msg: str) -> None:
        if self._prog_cb:
            self._prog_cb(d_sku, t_sku, msg)

    # ------------------------------------------------------------------
    # 紫鸟浏览器管理
    # ------------------------------------------------------------------
    def _start_ziniao_browser(self) -> int | None:
        """启动紫鸟客户端 + 店铺，返回调试端口。失败返回 None。"""
        # 1. 启动紫鸟客户端
        self._log("启动紫鸟浏览器客户端...")
        if not self.ziniao.start_client():
            self._log("紫鸟客户端启动失败，请检查 client_path 配置")
            return None

        # 2. 更新内核
        if not self.ziniao.update_core():
            self._log("紫鸟浏览器内核更新失败")
            return None

        # 3. 确定要启动的店铺
        shop_id = self._shop_id or self.ziniao.cfg.get("default_shop", "")
        if not shop_id:
            self._log("未配置紫鸟店铺ID，请在界面中选择店铺或配置默认店铺")
            return None

        # 4. 启动店铺
        self._log(f"启动紫鸟店铺: {shop_id}")
        result = self.ziniao.start_browser(shop_id, headless=False)
        if not result:
            self._log("紫鸟店铺启动失败")
            return None

        self._browser_started = True
        port = int(result.get("debuggingPort", 0))
        if port == 0:
            self._log("紫鸟返回的调试端口为空")
            return None
        return port

    def _stop_ziniao_browser(self) -> None:
        """关闭紫鸟店铺（不退出客户端）。"""
        if self._browser_started and self._shop_id:
            self._log("关闭紫鸟店铺...")
            self.ziniao.stop_browser(self._shop_id or self.ziniao.cfg.get("default_shop", ""))
            self._browser_started = False

    # ------------------------------------------------------------------
    # 进度文件
    # ------------------------------------------------------------------
    def _progress_path(self) -> str:
        return str((self.cfg.get("paths", {}) or {}).get("progress_file", "data/progress.json"))

    def _load_progress(self) -> set[str]:
        if self._completed_loader:
            try:
                return set(self._completed_loader())
            except Exception as exc:  # noqa: BLE001
                self._log(f"读取数据库断点记录失败，将按无断点执行: {exc}")
                return set()
        p = self._progress_path()
        if not os.path.exists(p):
            return set()
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("completed", []))
        except Exception:
            return set()

    def _save_progress(self, completed: set[str], latest_key: str | None = None) -> None:
        if self._completed_marker:
            if latest_key:
                self._completed_marker(latest_key)
            return
        p = self._progress_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(
                {"completed": sorted(completed), "updated_at": datetime.now().isoformat()},
                f,
                ensure_ascii=False,
                indent=2,
            )

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    async def run(self, excel_path: str, image_root: str, marketplace: dict[str, str]) -> None:
        """执行全部上传任务（单站点，其他站点自动同步）。"""
        self._stop_flag = False
        sku_col = str((self.cfg.get("excel", {}) or {}).get("sku_column", "SKU"))

        # 1. 读取 SKU
        try:
            skus = read_skus(excel_path, sku_col)
        except Exception as e:
            self._log(f"读取 Excel 失败: {e}")
            return
        if not skus:
            self._log("Excel 中没有可用的 SKU，结束")
            return
        self._log(f"共读取到 {len(skus)} 个 SKU")

        completed = self._load_progress()
        if completed:
            self._log(f"检测到历史进度，已完成 {len(completed)} 个任务，将跳过")

        total_sku = len(skus)
        code = marketplace["code"]
        domain = marketplace["domain"]

        # 2. 启动紫鸟浏览器 + 店铺
        debug_port = self._start_ziniao_browser()
        if debug_port is None:
            raise RuntimeError("紫鸟浏览器启动失败，任务终止")

        # 3. 连接浏览器
        try:
            await self.bot.start(debug_port)
        except Exception as e:
            detail = _exception_text(e)
            self._log(f"连接紫鸟浏览器失败: {detail}")
            await self.bot.close()
            self._stop_ziniao_browser()
            raise RuntimeError(f"连接紫鸟浏览器失败: {detail}") from e

        try:
            for i, sku in enumerate(skus, 1):
                if self._stop_flag:
                    self._log("已停止")
                    break

                # 检查图片是否就绪
                images = get_sku_images(sku, image_root)
                if not images:
                    expected = os.path.join(image_root, sku)
                    self._log(f"SKU {sku} 无图片，跳过")
                    self._log(f"  预期图片文件夹: {expected}")
                    self._log(f"  提示：图片根目录应包含以 SKU 命名的子文件夹，或直接选择 SKU 文件夹")
                    self._prog(i - 1, total_sku, f"SKU {sku} 无图片，跳过")
                    continue

                task_key = f"{sku}@{code}@{self._shop_id or 'default'}"
                if task_key in completed:
                    self._log(f"已完成，跳过: {task_key}")
                    self._prog(i - 1, total_sku, f"跳过 {task_key}")
                    continue

                self._prog(i - 1, total_sku, f"正在上传 {task_key}")
                success = await self._upload_one(sku, images, marketplace)

                if success:
                    completed.add(task_key)
                    self._save_progress(completed, task_key)
                    self._log(f"完成: {task_key}")
                else:
                    self._log(f"失败（跳过）: {task_key}")

                self._prog(i, total_sku, f"{task_key} {'OK' if success else 'FAIL'}")

            self._log("全部任务结束")
        finally:
            await self.bot.close()
            self._stop_ziniao_browser()

    async def run_multi(self, shop_tasks: list[dict[str, Any]], marketplace: dict[str, str]) -> None:
        """多店铺循环上传。

        shop_tasks 格式:
        [
            {"shop_id": "xxx", "shop_name": "店铺A", "excel_path": "...", "image_root": "..."},
            {"shop_id": "yyy", "shop_name": "店铺B", "excel_path": "...", "image_root": "..."},
        ]
        """
        self._stop_flag = False
        sku_col = str((self.cfg.get("excel", {}) or {}).get("sku_column", "SKU"))
        code = marketplace["code"]
        domain = marketplace["domain"]

        total_shops = len(shop_tasks)
        browser_attempts = 0
        browser_connections = 0
        self._log(f"========== 多店铺上传开始，共 {total_shops} 个店铺 ==========")

        for shop_idx, shop_task in enumerate(shop_tasks, 1):
            if self._stop_flag:
                self._log("已停止")
                break

            shop_id = shop_task["shop_id"]
            shop_name = shop_task.get("shop_name", shop_id)
            excel_path = shop_task["excel_path"]
            image_root = shop_task["image_root"]
            selected_images = shop_task.get("selected_images") or {}

            self._log(f"")
            self._log(f"========== 【{shop_idx}/{total_shops}】店铺: {shop_name} ==========")

            # 1. 读取该店铺的 SKU
            try:
                skus = read_skus(excel_path, sku_col)
            except Exception as e:
                self._log(f"读取 Excel 失败: {e}")
                continue
            if not skus:
                self._log("Excel 中没有可用的 SKU，跳过此店铺")
                continue

            # 如果指定了选中的SKU，只上传这些
            selected_skus = shop_task.get("selected_skus")
            if selected_skus:
                selected_set = set(selected_skus)
                skus = [s for s in skus if s in selected_set]
                self._log(f"用户选中 {len(selected_skus)} 个SKU，匹配到 {len(skus)} 个")
            else:
                self._log(f"共读取到 {len(skus)} 个 SKU")

            if not skus:
                self._log("没有可上传的SKU，跳过此店铺")
                continue

            # 2. 设置店铺ID并启动紫鸟
            browser_attempts += 1
            self.set_shop_id(shop_id)
            debug_port = self._start_ziniao_browser()
            if debug_port is None:
                self._log(f"店铺 {shop_name} 紫鸟浏览器启动失败，跳过")
                continue

            # 3. 连接浏览器
            try:
                await self.bot.start(debug_port)
            except Exception as e:
                detail = _exception_text(e)
                self._log(f"连接紫鸟浏览器失败: {detail}")
                await self.bot.close()
                self._stop_ziniao_browser()
                continue
            browser_connections += 1

            # 4. 循环上传该店铺的所有 SKU
            completed = self._load_progress()
            total_sku = len(skus)
            try:
                for i, sku in enumerate(skus, 1):
                    if self._stop_flag:
                        self._log("已停止")
                        break

                    available_images = get_sku_images(sku, image_root)
                    selected_names = {
                        str(name).casefold()
                        for name in (selected_images.get(sku) or [])
                    }
                    images = [
                        path for path in available_images
                        if os.path.basename(path).casefold() in selected_names
                    ]
                    if not images:
                        self._log(f"SKU {sku} 没有有效的已选图片，跳过")
                        self._prog(i - 1, total_sku, f"[{shop_name}] SKU {sku} 未选图片")
                        continue

                    self._log(f"SKU {sku} 本次仅上传已选的 {len(images)} 张图片")

                    # 同一 SKU 可以分多次选择不同图片上传。进度键必须包含
                    # 本次图片集合及文件版本，否则第一次完成后，后续新选的
                    # 图片会被旧的 SKU 级进度错误跳过。
                    signature_parts = []
                    for path in images:
                        stat = os.stat(path)
                        signature_parts.append(
                            f"{os.path.basename(path).casefold()}:{stat.st_size}:{stat.st_mtime_ns}"
                        )
                    selection_hash = hashlib.sha256(
                        "\n".join(signature_parts).encode("utf-8")
                    ).hexdigest()[:12]
                    task_key = f"{sku}@{code}@{shop_id}@{selection_hash}"
                    if task_key in completed:
                        self._log(f"已完成，跳过: {task_key}")
                        self._prog(i - 1, total_sku, f"[{shop_name}] 跳过 {sku}")
                        continue

                    self._prog(i - 1, total_sku, f"[{shop_name}] 正在上传 {sku}")
                    success = await self._upload_one(sku, images, marketplace)

                    if success:
                        completed.add(task_key)
                        self._save_progress(completed, task_key)
                        self._log(f"完成: {task_key}")
                    else:
                        self._log(f"失败（跳过）: {task_key}")

                    self._prog(i, total_sku, f"[{shop_name}] {sku} {'OK' if success else 'FAIL'}")

                self._log(f"店铺 {shop_name} 上传完成")
            finally:
                await self.bot.close()
                self._stop_ziniao_browser()

            # 5. 店铺切换前等待5-10秒（最后一个店铺不用等）
            if shop_idx < total_shops and not self._stop_flag:
                wait = random.uniform(5, 10)
                self._log(f"切换店铺前等待 {wait:.1f}秒...")
                await asyncio.sleep(wait)

        self._log(f"========== 全部店铺上传结束 ==========")
        if browser_attempts > 0 and browser_connections == 0:
            raise RuntimeError("所有店铺均未能连接紫鸟浏览器，请查看任务错误日志")

    async def _upload_one(
        self,
        sku: str,
        images: list[str],
        marketplace: dict[str, str],
    ) -> bool:
        """上传单个 SKU 的图片（单站点，其他站点自动同步）。"""
        code = marketplace["code"]
        domain = marketplace["domain"]
        try:
            self._log(f"打开 {domain} 库存页...")
            if not await self.bot.open_inventory(domain):
                self._log(f"  打开库存页失败: {sku}@{code}")
                return False
            await self._random_wait("打开库存页后")

            self._log(f"搜索 SKU: {sku}@{code}")
            if not await self.bot.search_sku(sku):
                self._log(f"  搜索 SKU 失败: {sku}@{code}")
                return False
            await self._random_wait("搜索SKU后")

            self._log(f"打开管理图片: {sku}@{code}")
            if not await self.bot.open_manage_images(sku):
                self._log(f"  打开管理图片失败: {sku}@{code}")
                return False
            await self._random_wait("打开管理图片后")

            self._log(f"上传 {len(images)} 张图片: {sku}@{code}")
            if not await self.bot.upload_images(images):
                self._log(f"  上传图片失败: {sku}@{code}")
                await self.bot.close_manage_images_tab()
                return False
            await self._random_wait("上传图片后")

            self._log(f"保存并完成: {sku}@{code}")
            if not await self.bot.save_and_complete():
                self._log(f"  保存失败: {sku}@{code}")
                await self.bot.close_manage_images_tab()
                return False
            await self._random_wait("保存完成后")

            return True
        except Exception as e:  # noqa: BLE001
            self._log(f"上传异常 {sku}@{code}: {e}")
            await self.bot.close_manage_images_tab()
            return False

    async def _random_wait(self, reason: str = "", min_sec: float = 1, max_sec: float = 5) -> None:
        """随机等待，模拟人工操作间隔，避免风控。"""
        wait = random.uniform(min_sec, max_sec)
        if reason:
            self._log(f"  随机等待 {wait:.1f}秒（{reason}）")
        await asyncio.sleep(wait)
