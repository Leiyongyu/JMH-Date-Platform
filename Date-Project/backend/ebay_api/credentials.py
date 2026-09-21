from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class EbayApiError(RuntimeError):
    """只包含安全诊断信息；禁止附带请求头、Token或响应正文。"""


def read_dpapi_token(path: str) -> str:
    """读取当前Windows用户的ConvertFrom-SecureString加密文件，不写明文。"""
    if os.name != 'nt' or not Path(path).is_file():
        raise EbayApiError('DPAPI文件不存在或当前系统不是Windows')
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = """
$ErrorActionPreference='Stop'
$encrypted=Get-Content -Raw -LiteralPath $env:JMH_EBAY_DPAPI_FILE
$secure=ConvertTo-SecureString $encrypted
$token=[System.Net.NetworkCredential]::new('', $secure).Password
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
[Console]::Write($token)
"""
    environment = {key: value for key, value in os.environ.items() if key.lower() != 'psmodulepath'}
    environment['JMH_EBAY_DPAPI_FILE'] = str(Path(path).resolve())
    # PowerShell 7的PSModulePath会使Windows PowerShell 5找不到其Security模块。
    # 让子进程按自身版本重建模块路径，而不是继承父进程版本。
    try:
        result = subprocess.run([str(executable), '-NoProfile', '-NonInteractive', '-Command', script],
                                env=environment,
                                capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        raise EbayApiError('DPAPI读取失败，请使用创建凭证的Windows账户运行') from None
    if result.returncode != 0:
        raise EbayApiError('DPAPI解密失败，请检查Windows账户及凭证文件')
    token = result.stdout.decode('utf-8-sig').strip()
    if not token:
        raise EbayApiError('DPAPI凭证为空')
    return token


@dataclass(frozen=True)
class EbayCredentials:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    refresh_token: str = field(repr=False)

    @classmethod
    def from_env(cls, *, token_file: str | None = None) -> 'EbayCredentials':
        # 与本项目其他服务一致，加载Date-Project/.env；不读取其他项目配置。
        from backend.config import load_dotenv
        load_dotenv()
        client_id = os.getenv('EBAY_CLIENT_ID', '').strip()
        secret = os.getenv('EBAY_CLIENT_SECRET', '').strip()
        if not client_id or not secret:
            raise EbayApiError('请配置EBAY_CLIENT_ID和EBAY_CLIENT_SECRET')
        configured_file = token_file or os.getenv('EBAY_REFRESH_TOKEN_DPAPI_FILE', '').strip()
        token = read_dpapi_token(configured_file) if configured_file else os.getenv('EBAY_REFRESH_TOKEN', '').strip()
        if not token:
            raise EbayApiError('请配置店铺EBAY_REFRESH_TOKEN或EBAY_REFRESH_TOKEN_DPAPI_FILE')
        return cls(client_id, secret, token)
