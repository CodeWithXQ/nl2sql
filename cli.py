"""命令行入口：自然语言问数。

用法：
    python cli.py "待支付的订单有多少"
    python cli.py "北京的用户有多少" --user ops
"""
from __future__ import annotations

import argparse

from agent import get_conn, query


def main() -> None:
    parser = argparse.ArgumentParser(description="NL2SQL 自助取数 Agent")
    parser.add_argument("question", help="自然语言问题")
    parser.add_argument("--user", default="analyst", help="用户名（决定表级权限）")
    args = parser.parse_args()

    conn = get_conn()
    try:
        _print(query(args.question, args.user, conn=conn))
    finally:
        conn.close()


def _print(result: dict) -> None:
    if not result["ok"]:
        print(f"拒绝执行：{result['reason']}")
        print(f"生成的 SQL：{result['sql']}")
        return

    print(f"生成的 SQL：{result['sql']}")
    r = result["result"]
    if "error" in r:
        print(f"执行失败：{r['error']}")
        return

    print(f"结果（{r['row_count']} 行）：")
    cols = r["columns"]
    for row in r["rows"][:20]:
        print("  " + " | ".join(f"{c}={v}" for c, v in zip(cols, row)))
    if r["row_count"] > 20:
        print(f"  ... 共 {r['row_count']} 行")


if __name__ == "__main__":
    main()
