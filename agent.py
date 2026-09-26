"""主流程编排：自然语言问题 → Schema 对齐 → SQL 生成 → 四道关校验 → 执行。"""
from __future__ import annotations

import pymysql

from config import get_mysql_config
from executor import Executor
from rbac import RBAC
from schema_manager import SchemaManager
from sql_generator import SQLGenerator
from sql_validator import validate


def get_conn() -> pymysql.connections.Connection:
    cfg = get_mysql_config()
    return pymysql.connect(**cfg)


def query(question: str, user: str, conn=None, rbac: RBAC | None = None,
          generator: SQLGenerator | None = None) -> dict:
    """完整 NL2SQL 流程。返回 dict：{ok, sql, result, validation, reason}。"""
    own_conn = conn is None
    if own_conn:
        conn = get_conn()

    rbac = rbac or RBAC()
    generator = generator or SQLGenerator()
    schema_mgr = SchemaManager(conn)

    try:
        authorized = rbac.authorized_tables(user)
        # LLM 看全部表结构（才能理解问题语义），权限由校验器拦截
        schema_text = schema_mgr.get_schema_text()

        sql = generator.generate(question, schema_text, authorized)

        vr = validate(sql, user, rbac)
        if not vr.ok:
            return {"ok": False, "sql": sql, "validation": vr, "reason": vr.reason}

        executor = Executor(conn)
        result = executor.execute(sql)
        return {"ok": True, "sql": sql, "result": result, "validation": vr}
    finally:
        if own_conn:
            conn.close()
