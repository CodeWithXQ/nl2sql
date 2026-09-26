"""RBAC 表级权限：用户 → 授权表映射，越权拦截。"""
from __future__ import annotations


class PermissionDenied(Exception):
    def __init__(self, tables: list[str], authorized: list[str]):
        self.tables = tables
        self.authorized = authorized
        super().__init__(f"越权访问：涉及表 {tables}，授权表 {authorized}")


class RBAC:
    def __init__(self, permissions: dict[str, list[str]] | None = None):
        # 默认权限配置（演示用静态配置，生产接真实权限系统）
        self._permissions = permissions or {
            "analyst": ["orders", "users", "products"],
            "ops": ["orders"],
            "guest": [],
        }

    def authorized_tables(self, user: str) -> list[str]:
        return self._permissions.get(user, [])

    def check(self, user: str, tables: list[str]) -> None:
        """校验涉及的表是否都在授权范围内，越权抛 PermissionDenied。"""
        allowed = set(self.authorized_tables(user))
        for t in tables:
            if t not in allowed:
                raise PermissionDenied(tables, list(allowed))
