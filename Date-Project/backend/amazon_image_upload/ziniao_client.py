"""紫鸟浏览器 HTTP API 客户端。

封装紫鸟浏览器的本地 HTTP 接口，实现：
- 启动紫鸟客户端（webdriver 模式）
- 更新浏览器内核
- 获取店铺列表
- 启动/关闭指定店铺
- 退出客户端

接口文档：https://open.ziniao.com/docSupport?docId=98
所有请求均为 POST JSON，发往 http://127.0.0.1:{socket_port}
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
import uuid
from typing import Any

import requests
from loguru import logger


class ZiniaoClient:
    """紫鸟浏览器本地 API 客户端。"""

    def __init__(self, ziniao_cfg: dict[str, Any]):
        self.cfg = ziniao_cfg
        self.client_path: str = ziniao_cfg.get("client_path", "")
        self.socket_port: int = int(ziniao_cfg.get("socket_port", 16851))
        self.company: str = ziniao_cfg.get("company", "")
        self.username: str = ziniao_cfg.get("username", "")
        self.password: str = ziniao_cfg.get("password", "")
        self.user_info = {
            "company": self.company,
            "username": self.username,
            "password": self.password,
        }
        self._client_started = False
        self._verbose = True  # 启动阶段打印详细错误

    # ------------------------------------------------------------------
    # 内部通信
    # ------------------------------------------------------------------
    def _send(self, data: dict, timeout: int = 30) -> dict | None:
        """发送 HTTP 请求到紫鸟客户端。"""
        url = f"http://127.0.0.1:{self.socket_port}"
        payload = json.dumps(data).encode("utf-8")
        try:
            resp = requests.post(url, data=payload, timeout=timeout)
            text = resp.text.strip()
            if not text:
                return {}
            return json.loads(text)
        except requests.exceptions.ConnectionError as e:
            if self._verbose:
                logger.debug("紫鸟 HTTP 连接失败 (端口 {} 未就绪): {}", self.socket_port, e)
            return None
        except Exception as e:
            if self._verbose:
                logger.warning("紫鸟 HTTP 请求异常: {}", e)
            return None

    def _build_request(self, action: str, **extra) -> dict:
        """构造请求体。"""
        req = {
            "action": action,
            "requestId": str(uuid.uuid4()),
        }
        req.update(self.user_info)
        req.update(extra)
        return req

    @staticmethod
    def _is_success(result: dict | None) -> bool:
        return result is not None and str(result.get("statusCode")) == "0"

    # ------------------------------------------------------------------
    # 客户端生命周期
    # ------------------------------------------------------------------
    def _is_process_running(self) -> bool:
        """检测是否有紫鸟进程在运行。"""
        exe_name = os.path.basename(self.client_path) if self.client_path else "ziniao.exe"
        try:
            if platform.system() == "Windows":
                output = subprocess.check_output(
                    ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"],
                    encoding="gbk",
                    errors="ignore",
                )
                return exe_name.lower() in output.lower()
            else:
                output = subprocess.check_output(["pgrep", "-f", exe_name], text=True)
                return bool(output.strip())
        except Exception:
            return False

    def _wait_for_http(self, max_wait: int = 60) -> bool:
        """等待紫鸟 HTTP 接口就绪。"""
        start = time.time()
        while time.time() - start < max_wait:
            result = self._ping()
            if result:
                return True
            time.sleep(1)
        return False

    def start_client(self) -> bool:
        """启动紫鸟客户端（webdriver 模式）。"""
        # 如果 HTTP 接口已在运行，直接复用
        if self._ping():
            logger.info("紫鸟 HTTP 接口已在运行，跳过启动")
            self._client_started = False
            return True

        if not self.client_path or not os.path.exists(self.client_path):
            logger.error("紫鸟客户端路径不存在: {}", self.client_path)
            return False

        if not self.company or not self.username or not self.password:
            logger.error("紫鸟企业账号信息未配置，请检查 Date-Project 的 AMAZON_IMAGE_UPLOAD_ZINIAO_* 环境变量")
            return False

        is_windows = platform.system() == "Windows"
        is_mac = platform.system() == "Darwin"

        if is_windows:
            cmd = [
                self.client_path,
                "--run_type=web_driver",
                "--ipc_type=http",
                f"--port={self.socket_port}",
            ]
        elif is_mac:
            cmd = [
                "open",
                "-a",
                self.client_path,
                "--args",
                "--run_type=web_driver",
                "--ipc_type=http",
                f"--port={self.socket_port}",
            ]
        else:
            cmd = [
                self.client_path,
                "--no-sandbox",
                "--run_type=web_driver",
                "--ipc_type=http",
                f"--port={self.socket_port}",
            ]

        logger.info("启动紫鸟客户端: {}", self.client_path)
        logger.info("自动化参数: run_type=web_driver, ipc_type=http, port={}", self.socket_port)

        try:
            # 使用 CREATE_NEW_CONSOLE 让子进程独立，避免随父进程退出
            kwargs = {}
            if is_windows:
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen(cmd, **kwargs)
        except Exception as e:
            logger.error("启动紫鸟客户端失败: {}", e)
            return False

        self._client_started = True

        # 等待 HTTP 接口就绪
        logger.info("等待紫鸟 HTTP 接口就绪，最长 60 秒...")
        if not self._wait_for_http(max_wait=60):
            logger.error("紫鸟 HTTP 接口未就绪，请检查：")
            logger.error("  1. 紫鸟客户端是否已正常启动")
            logger.error("  2. 端口 {} 是否被其他程序占用", self.socket_port)
            logger.error("  3. 紫鸟账号是否开通了 webdriver 自动化权限")
            return False

        logger.info("紫鸟客户端已就绪")
        return True

    def _ping(self) -> bool:
        """检测紫鸟客户端是否在运行。"""
        result = self._send(self._build_request("getRunningInfo"), timeout=5)
        return result is not None

    def update_core(self, max_wait: int = 300) -> bool:
        """更新浏览器内核，循环调用直到成功。"""
        logger.info("检查紫鸟浏览器内核...")
        data = self._build_request("updateCore")
        start = time.time()
        last_msg = ""
        while time.time() - start < max_wait:
            result = self._send(data, timeout=30)
            if result is None:
                logger.info("等待紫鸟客户端启动...")
                time.sleep(2)
                continue

            code = result.get("statusCode")
            msg = result.get("msg", result.get("err", ""))

            if code is None:
                logger.error("紫鸟返回异常: {}", result)
                return False

            if str(code) == "-10003":
                logger.error("紫鸟版本不支持此接口或登录失败: {}", result)
                return False

            if str(code) == "0":
                logger.info("紫鸟浏览器内核就绪")
                return True

            # 避免重复日志刷屏
            if msg != last_msg:
                logger.info("等待内核更新: {} (code={})", msg, code)
                last_msg = msg
            time.sleep(2)

        logger.error("内核更新超时")
        return False

    def exit_client(self) -> None:
        """退出紫鸟客户端。"""
        if not self._client_started:
            logger.info("紫鸟客户端非本程序启动，跳过退出")
            return
        logger.info("退出紫鸟客户端")
        self._send(self._build_request("exit"))
        self._wait_until_stopped()
        self._client_started = False

    def force_exit_client(self) -> None:
        """Release this configured port before assigning it to another account."""
        if not self._ping():
            self._client_started = False
            return
        logger.info("清理紫鸟自动化端口: {}", self.socket_port)
        self._send(self._build_request("exit"), timeout=10)
        self._wait_until_stopped()
        self._client_started = False

    def _wait_until_stopped(self, max_wait: int = 15) -> None:
        deadline = time.time() + max_wait
        old_verbose = self._verbose
        self._verbose = False
        try:
            while time.time() < deadline:
                if not self._ping():
                    return
                time.sleep(0.5)
        finally:
            self._verbose = old_verbose

    # ------------------------------------------------------------------
    # 店铺管理
    # ------------------------------------------------------------------
    def get_browser_list(self) -> list[dict]:
        """获取店铺列表。"""
        result = self._send(self._build_request("getBrowserList"))
        if not self._is_success(result):
            logger.error("获取店铺列表失败: {}", result)
            return []
        shops = result.get("browserList", [])
        logger.info("获取到 {} 个紫鸟店铺", len(shops))
        return shops

    def start_browser(self, shop_id: str, headless: bool = False) -> dict | None:
        """启动指定店铺，返回包含 debuggingPort 等信息的字典。"""
        extra: dict[str, Any] = {
            "isWaitPluginUpdate": 0,
            "isHeadless": 1 if headless else 0,
            "isWebDriverReadOnlyMode": 0,
            "cookieTypeLoad": 0,
            "cookieTypeSave": 0,
            "runMode": "1",
            "isLoadUserPlugin": False,
            "pluginIdType": 1,
            "privacyMode": 0,
        }
        if shop_id.isdigit():
            extra["browserId"] = shop_id
        else:
            extra["browserOauth"] = shop_id

        result = self._send(self._build_request("startBrowser", **extra), timeout=120)
        if not self._is_success(result):
            logger.error("启动店铺失败: {}", result)
            return None

        port = result.get("debuggingPort")
        if not port:
            logger.error("启动店铺成功但未返回调试端口: {}", result)
            return None

        logger.info("店铺已启动，调试端口: {}", port)
        return result

    def stop_browser(self, shop_id: str) -> bool:
        """关闭指定店铺窗口。"""
        extra: dict[str, Any] = {"duplicate": 0}
        if shop_id.isdigit():
            extra["browserId"] = shop_id
        else:
            extra["browserOauth"] = shop_id

        result = self._send(self._build_request("stopBrowser", **extra))
        ok = self._is_success(result)
        if ok:
            logger.info("店铺已关闭: {}", shop_id)
        else:
            logger.warning("关闭店铺失败: {}", result)
        return ok
