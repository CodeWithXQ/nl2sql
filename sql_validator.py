"""SQL 校验器：四道关（语法/只读/权限/注入），缺一不可，任意不过即拦截。

用 sqlglot 做 SQL 解析（语法 / 语句类型 / 表名提取），
校验逻辑（只读判断 / 权限比对 / 注入黑名单）自己写。
"""
from __future__ import annotations

import re

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp

from rbac import PermissionDenied

# 只读语句类型（SELECT 及其组合查询）
_READ_ONLY_TYPES = (exp.Select, exp.Union, exp.Except, exp.Intersect)

# 补充注入黑名单（只读+单语句已挡大部分，这里再兜高风险关键字）
_DANGEROUS_PATTERNS = [
    r"\bINTO\s+OUTFILE\b",
    r"\bINTO\s+DUMPFILE\b",
    r"\bLOAD_FILE\b",
    r"\bSLEEP\s*\(",
    r"\bBENCHMARK\s*\(",
]


class ValidationResult(BaseModel):
    ok: bool
    sql: str = ""
    reason: str = ""
    tables: list[str] = Field(default_factory=list)
    checks: dict = Field(default_factory=dict)


def validate(sql: str, user: str, rbac) -> ValidationResult:
    """四道关校验，返回 ValidationResult。"""
    checks: dict = {}
    sql = sql.strip().rstrip(";").strip()

    # 关1 语法 + 多语句检测（sqlglot parse 多条）
    try:
        statements = sqlglot.parse(sql, read="mysql")
    except Exception as e:  # noqa: BLE001
        checks["syntax"] = False
        return ValidationResult(ok=False, sql=sql, reason=f"SQL 语法错误：{e}", checks=checks)
    if len(statements) != 1:
        checks["syntax"] = False
        checks["injection"] = False
        return ValidationResult(
            ok=False, sql=sql, reason=f"检测到多语句（{len(statements)} 条），拒绝执行", checks=checks
        )
    checks["syntax"] = True

    stmt = statements[0]

    # 关2 只读校验（仅放行 SELECT 及组合查询）
    if not isinstance(stmt, _READ_ONLY_TYPES):
        kind = stmt.key.upper() if stmt and stmt.key else "未知"
        checks["readonly"] = False
        return ValidationResult(ok=False, sql=sql, reason=f"仅允许 SELECT，检测到 {kind}", checks=checks)
    checks["readonly"] = True

    # 关3 表名提取 + 表级权限
    tables = [t.name for t in stmt.find_all(exp.Table) if t.name]
    try:
        rbac.check(user, tables)
        checks["permission"] = True
    except PermissionDenied as e:
        checks["permission"] = False
        return ValidationResult(ok=False, sql=sql, reason=str(e), tables=tables, checks=checks)

    # 关4 注入黑名单兜底（高风险关键字）
    upper = sql.upper()
    for pat in _DANGEROUS_PATTERNS:
        if re.search(pat, upper):
            checks["injection"] = False
            return ValidationResult(ok=False, sql=sql, reason=f"检测到注入尝试：{pat}", checks=checks)
    checks["injection"] = True

    return ValidationResult(ok=True, sql=sql, tables=tables, checks=checks)
