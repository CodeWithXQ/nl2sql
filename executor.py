"""执行器：执行通过四道关校验的 SQL，返回结果。

生产建议用只读 MySQL 用户（GRANT SELECT）建立连接，这里 SQL 已过只读校验，
执行层是纵深防御。执行失败（如列不存在）时返回错误而非抛出，供评测统计。
"""
from __future__ import annotations


class Executor:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str) -> dict:
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
            return {"columns": cols, "rows": rows, "row_count": len(rows)}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
        finally:
            cur.close()
