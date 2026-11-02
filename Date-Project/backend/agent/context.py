from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

ADMIN_PERMISSION = "*:*:*"

# 与 Java BusinessDataScopeService 的模块编码一致。
SCOPE_EBAY = "operations:ebayReplenishmentV2"
SCOPE_AMZ = "operations:amzReplenishment"
KNOWN_SCOPES = (SCOPE_EBAY, SCOPE_AMZ)


class ToolPermissionError(PermissionError):
    """当前登录用户没有该工具对应页面的权限。"""


@dataclass(frozen=True)
class AgentAccess:
    """Java 网关根据登录用户计算出的权限，聊天内容无法修改。

    ``scopes`` 中 ``None`` 表示全部数据，``[]`` 表示无数据，列表表示允许的负责人。
    未出现的模块按无数据处理。
    """

    permissions: frozenset[str] = frozenset()
    scopes: dict[str, list[str] | None] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict | None) -> "AgentAccess":
        payload = payload or {}
        permissions = frozenset(
            str(item).strip() for item in payload.get("permissions") or [] if str(item).strip()
        )
        scopes: dict[str, list[str] | None] = {}
        raw_scopes = payload.get("scopes") or {}
        for module in KNOWN_SCOPES:
            if module not in raw_scopes:
                continue
            value = raw_scopes[module]
            if value is None:
                scopes[module] = None
            elif isinstance(value, list):
                scopes[module] = list(dict.fromkeys(
                    str(item).strip() for item in value if str(item).strip()
                ))
        return cls(permissions=permissions, scopes=scopes)

    @property
    def is_admin(self) -> bool:
        return ADMIN_PERMISSION in self.permissions

    def has(self, permission: str) -> bool:
        return self.is_admin or permission in self.permissions

    def scope(self, module: str) -> list[str] | None:
        if self.is_admin:
            return None
        return self.scopes.get(module, [])


@dataclass(frozen=True)
class AgentContext:
    user_id: int
    username: str
    access: AgentAccess
    request_id: str = ""
    today: date = field(default_factory=date.today)

    def require(self, permission: str) -> None:
        if not self.access.has(permission):
            raise ToolPermissionError(f"当前账号没有「{permission}」权限，不能查询该数据")
