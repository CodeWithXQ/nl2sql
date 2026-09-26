"""Schema 管理：读取真实 MySQL 表结构，生成喂给 LLM 的 schema 摘要。

核心作用：让 LLM 生成 SQL 时只能基于真实表名/列名，从源头抑制"编造列名"幻觉。
"""
from __future__ import annotations


class SchemaManager:
    def __init__(self, conn):
        self._conn = conn

    def get_tables(self) -> list[str]:
        cur = self._conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [r[0] for r in cur.fetchall()]
        cur.close()
        return tables

    def get_schema_text(self, tables: list[str] | None = None) -> str:
        """生成 schema 摘要文本（SHOW CREATE TABLE 结果拼接），喂给 LLM。"""
        if tables is None:
            tables = self.get_tables()
        parts = []
        cur = self._conn.cursor()
        for t in tables:
            try:
                cur.execute(f"SHOW CREATE TABLE `{t}`")
                row = cur.fetchone()
                if row:
                    parts.append(row[1])
            except Exception:  # noqa: BLE001
                continue
        cur.close()
        parts.append(self._enum_hints())
        return "\n\n".join(parts)

    def _enum_hints(self) -> str:
        """枚举列取值说明：让 LLM 把问题中的中文描述映射到真实存储值。"""
        return (
            "# 枚举列取值说明（问题里的中文描述需映射到下面这些实际存储值）\n"
            "orders.status: 'pending'(待支付) / 'paid'(已支付) / 'shipped'(已发货) / 'done'(已完成)\n"
            "users.level: '普通' / '银卡' / '金卡' / '钻石'\n"
            "products.category: '手机' / '电脑' / '家电' / '服饰' / '美妆' / '食品' / '图书' / '运动' / '家居' / '数码'"
        )
