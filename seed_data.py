"""造数脚本：在 db_doctor 库新建 users（10万行）+ products（1000行），复用 orders。

orders 表已由 db-doctor 造好（100 万行），这里只补 users/products 两张表，
凑成 3 表 schema，让 NL2SQL 能展示 join 能力。
"""
from __future__ import annotations

import random

import pymysql

from config import get_mysql_config

CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京", "重庆"]
LEVELS = ["普通", "银卡", "金卡", "钻石"]
CATEGORIES = ["手机", "电脑", "家电", "服饰", "美妆", "食品", "图书", "运动", "家居", "数码"]


def setup() -> None:
    cfg = get_mysql_config()
    db = cfg["database"]
    conn = pymysql.connect(
        host=cfg["host"], port=cfg["port"], user=cfg["user"],
        password=cfg["password"], charset=cfg["charset"],
    )
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db}` DEFAULT CHARACTER SET utf8mb4")
    cur.execute(f"USE `{db}`")

    cur.execute("DROP TABLE IF EXISTS users")
    cur.execute(
        "CREATE TABLE users ("
        "id BIGINT PRIMARY KEY AUTO_INCREMENT, "
        "name VARCHAR(50) NOT NULL, "
        "city VARCHAR(20) NOT NULL, "
        "level VARCHAR(10) NOT NULL"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    )
    cur.execute("DROP TABLE IF EXISTS products")
    cur.execute(
        "CREATE TABLE products ("
        "id BIGINT PRIMARY KEY AUTO_INCREMENT, "
        "name VARCHAR(100) NOT NULL, "
        "category VARCHAR(20) NOT NULL, "
        "price DECIMAL(10,2) NOT NULL"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    )
    conn.commit()

    print("插入 users 100000 行...")
    batch = 5000
    for i in range(100000 // batch):
        data = [
            (f"用户{random.randint(1, 999999)}", random.choice(CITIES), random.choice(LEVELS))
            for _ in range(batch)
        ]
        cur.executemany("INSERT INTO users (name, city, level) VALUES (%s, %s, %s)", data)
        conn.commit()
        if (i + 1) % 5 == 0:
            print(f"  users {(i + 1) * batch:,}")

    print("插入 products 1000 行...")
    data = []
    for j in range(1000):
        cat = random.choice(CATEGORIES)
        data.append((f"{cat}商品{j}", cat, round(random.uniform(10, 10000), 2)))
    cur.executemany("INSERT INTO products (name, category, price) VALUES (%s, %s, %s)", data)
    conn.commit()

    cur.close()
    conn.close()
    print("造数完成")


if __name__ == "__main__":
    setup()
