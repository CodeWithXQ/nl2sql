"""评测脚本：生成 SQL 正确率 + 越权拦截率 + 注入拦截率。

用法：
    python seed_data.py   # 先造数
    python evaluate.py    # 再评测
"""
from __future__ import annotations

from agent import get_conn
from rbac import RBAC
from schema_manager import SchemaManager
from sql_generator import SQLGenerator
from sql_validator import validate

# 50 条 NL2SQL 测试集：(自然语言问题, 期望 SQL)
TESTSET: list[tuple[str, str]] = [
    # --- 单表 orders ---
    ("待支付的订单有多少", "SELECT COUNT(*) FROM orders WHERE status='pending'"),
    ("订单总金额是多少", "SELECT SUM(amount) FROM orders"),
    ("平均每笔订单金额", "SELECT AVG(amount) FROM orders"),
    ("金额大于5000的订单数量", "SELECT COUNT(*) FROM orders WHERE amount>5000"),
    ("已发货的订单数量", "SELECT COUNT(*) FROM orders WHERE status='shipped'"),
    ("金额最高的5笔订单", "SELECT * FROM orders ORDER BY amount DESC LIMIT 5"),
    ("订单总数", "SELECT COUNT(*) FROM orders"),
    ("金额在100到200之间的订单数", "SELECT COUNT(*) FROM orders WHERE amount BETWEEN 100 AND 200"),
    ("订单状态有几种", "SELECT COUNT(DISTINCT status) FROM orders"),
    ("已完成的订单总金额", "SELECT SUM(amount) FROM orders WHERE status='done'"),
    # --- 单表 users ---
    ("用户总数", "SELECT COUNT(*) FROM users"),
    ("北京的用户有多少", "SELECT COUNT(*) FROM users WHERE city='北京'"),
    ("钻石会员有多少人", "SELECT COUNT(*) FROM users WHERE level='钻石'"),
    ("每个城市的用户数量", "SELECT city, COUNT(*) FROM users GROUP BY city"),
    ("金卡和钻石会员总人数", "SELECT COUNT(*) FROM users WHERE level IN ('金卡','钻石')"),
    ("上海和广州的用户总数", "SELECT COUNT(*) FROM users WHERE city IN ('上海','广州')"),
    # --- 单表 products ---
    ("商品总数", "SELECT COUNT(*) FROM products"),
    ("手机类商品有多少", "SELECT COUNT(*) FROM products WHERE category='手机'"),
    ("价格最高的商品", "SELECT * FROM products ORDER BY price DESC LIMIT 1"),
    ("每个品类的商品数量", "SELECT category, COUNT(*) FROM products GROUP BY category"),
    ("价格超过5000的商品数量", "SELECT COUNT(*) FROM products WHERE price>5000"),
    ("图书类商品的平均价格", "SELECT AVG(price) FROM products WHERE category='图书'"),
    # --- JOIN orders + users ---
    ("北京用户的订单数", "SELECT COUNT(*) FROM orders o JOIN users u ON o.user_id=u.id WHERE u.city='北京'"),
    ("每个城市的订单数", "SELECT u.city, COUNT(o.id) FROM orders o JOIN users u ON o.user_id=u.id GROUP BY u.city"),
    ("钻石会员的订单总额", "SELECT SUM(o.amount) FROM orders o JOIN users u ON o.user_id=u.id WHERE u.level='钻石'"),
    ("上海用户的待支付订单数", "SELECT COUNT(*) FROM orders o JOIN users u ON o.user_id=u.id WHERE u.city='上海' AND o.status='pending'"),
    ("各等级用户的平均订单金额", "SELECT u.level, AVG(o.amount) FROM orders o JOIN users u ON o.user_id=u.id GROUP BY u.level"),
    ("深圳用户的已发货订单数", "SELECT COUNT(*) FROM orders o JOIN users u ON o.user_id=u.id WHERE u.city='深圳' AND o.status='shipped'"),
    ("杭州用户的订单总额", "SELECT SUM(o.amount) FROM orders o JOIN users u ON o.user_id=u.id WHERE u.city='杭州'"),
    ("金卡用户的下单数量", "SELECT COUNT(*) FROM orders o JOIN users u ON o.user_id=u.id WHERE u.level='金卡'"),
    # --- 更多 JOIN / 复杂（orders 无 product 关联字段，不设 orders+products 的 JOIN）---
    ("每个城市订单总金额", "SELECT u.city, SUM(o.amount) FROM orders o JOIN users u ON o.user_id=u.id GROUP BY u.city"),
    ("订单数最多的城市是哪个", "SELECT u.city FROM orders o JOIN users u ON o.user_id=u.id GROUP BY u.city ORDER BY COUNT(*) DESC LIMIT 1"),
    ("银卡用户的订单数", "SELECT COUNT(*) FROM orders o JOIN users u ON o.user_id=u.id WHERE u.level='银卡'"),
    ("每个状态的平均订单金额", "SELECT status, AVG(amount) FROM orders GROUP BY status"),
    # --- 组合 / 复杂 ---
    ("订单金额降序排列的前3笔", "SELECT * FROM orders ORDER BY amount DESC LIMIT 3"),
    ("状态为已支付的订单，按金额升序", "SELECT * FROM orders WHERE status='paid' ORDER BY amount ASC"),
    ("每个状态订单的总金额", "SELECT status, SUM(amount) FROM orders GROUP BY status"),
    ("订单金额的最大值和最小值", "SELECT MAX(amount), MIN(amount) FROM orders"),
    ("金额最大的用户编号", "SELECT user_id FROM orders ORDER BY amount DESC LIMIT 1"),
    ("下单次数最多的用户编号", "SELECT user_id FROM orders GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 1"),
    ("非待支付状态的订单数", "SELECT COUNT(*) FROM orders WHERE status<>'pending'"),
    ("金额不低于10000的订单数", "SELECT COUNT(*) FROM orders WHERE amount>=10000"),
    ("备注非空的订单数", "SELECT COUNT(*) FROM orders WHERE remark IS NOT NULL"),
    ("每个城市的钻石会员数", "SELECT city, COUNT(*) FROM users WHERE level='钻石' GROUP BY city"),
    ("商品价格在100到1000之间的数量", "SELECT COUNT(*) FROM products WHERE price BETWEEN 100 AND 1000"),
    ("订单状态为已发货或已完成的数量", "SELECT COUNT(*) FROM orders WHERE status IN ('shipped','done')"),
    ("北京用户中金卡会员的数量", "SELECT COUNT(*) FROM users WHERE city='北京' AND level='金卡'"),
    ("各品类商品的平均价格", "SELECT category, AVG(price) FROM products GROUP BY category"),
    ("订单金额排名前10的平均金额", "SELECT AVG(amount) FROM (SELECT amount FROM orders ORDER BY amount DESC LIMIT 10) t"),
    ("每个等级用户的订单数", "SELECT u.level, COUNT(o.id) FROM orders o JOIN users u ON o.user_id=u.id GROUP BY u.level"),
    # --- 复杂查询（LLM 易错点：HAVING / NOT IN / 子查询比较 / 枚举"及以上"语义）---
    ("订单数超过10的城市", "SELECT u.city FROM orders o JOIN users u ON o.user_id=u.id GROUP BY u.city HAVING COUNT(*)>10"),
    ("没有下过订单的用户数量", "SELECT COUNT(*) FROM users WHERE id NOT IN (SELECT user_id FROM orders)"),
    ("下单金额高于平均值的订单数量", "SELECT COUNT(*) FROM orders WHERE amount>(SELECT AVG(amount) FROM orders)"),
    ("订单总金额超过50000的城市", "SELECT u.city FROM orders o JOIN users u ON o.user_id=u.id GROUP BY u.city HAVING SUM(o.amount)>50000"),
    ("价格高于平均价格的商品数量", "SELECT COUNT(*) FROM products WHERE price>(SELECT AVG(price) FROM products)"),
    ("每个城市金额最高的订单金额", "SELECT u.city, MAX(o.amount) FROM orders o JOIN users u ON o.user_id=u.id GROUP BY u.city"),
    ("订单金额排名前5的用户所在城市", "SELECT u.city FROM orders o JOIN users u ON o.user_id=u.id GROUP BY u.user_id, u.city ORDER BY SUM(o.amount) DESC LIMIT 5"),
    ("银卡及以上会员的订单总金额", "SELECT SUM(o.amount) FROM orders o JOIN users u ON o.user_id=u.id WHERE u.level IN ('银卡','金卡','钻石')"),
]


def _execute(conn, sql: str) -> set | None:
    cur = conn.cursor()
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        return set(rows)
    except Exception:  # noqa: BLE001
        return None
    finally:
        cur.close()


def run_accuracy() -> float:
    """生成 SQL 正确率：结果集比对。"""
    conn = get_conn()
    generator = SQLGenerator()
    rbac = RBAC()
    schema_mgr = SchemaManager(conn)
    authorized = rbac.authorized_tables("analyst")
    schema_text = schema_mgr.get_schema_text(authorized)

    hit = 0
    misses = []
    for question, expected_sql in TESTSET:
        generated = generator.generate(question, schema_text, authorized)
        vr = validate(generated, "analyst", rbac)
        if not vr.ok:
            misses.append((question, expected_sql, generated, f"校验未过:{vr.reason}"))
            continue
        exp_rows = _execute(conn, expected_sql)
        got_rows = _execute(conn, generated)
        if exp_rows is not None and got_rows is not None and exp_rows == got_rows:
            hit += 1
        else:
            misses.append((question, expected_sql, generated, "结果不一致"))

    total = len(TESTSET)
    acc = hit / total
    print(f"生成 SQL 正确率：{hit}/{total} = {acc * 100:.1f}%")
    for q, exp, got, why in misses[:10]:
        print(f"  [MISS] {q} | 期望:{exp} | 生成:{got} | {why}")
    conn.close()
    return acc


def run_security() -> None:
    """越权 + 注入拦截率（纯校验器，不调 LLM）。"""
    rbac = RBAC()

    # 越权样本：ops 只能查 orders
    perm_samples = [
        ("SELECT * FROM users", "ops"),
        ("SELECT * FROM products", "ops"),
        ("SELECT * FROM users WHERE city='北京'", "ops"),
        ("SELECT id FROM products", "guest"),
        ("SELECT * FROM orders o JOIN users u ON o.user_id=u.id", "ops"),
        # 绕过样本：子查询 / CTE / 标量子查询 / EXISTS 试图访问无权限表
        ("SELECT * FROM (SELECT * FROM users) t", "ops"),
        ("WITH x AS (SELECT * FROM users) SELECT * FROM x", "ops"),
        ("SELECT * FROM orders WHERE user_id IN (SELECT id FROM users)", "ops"),
        ("SELECT (SELECT city FROM users LIMIT 1) FROM orders", "ops"),
        ("SELECT * FROM orders o WHERE EXISTS (SELECT 1 FROM users u WHERE u.id=o.user_id AND u.city='北京')", "ops"),
    ]
    blocked = sum(1 for sql, u in perm_samples if not validate(sql, u, rbac).ok)
    print(f"越权拦截率：{blocked}/{len(perm_samples)} = {blocked / len(perm_samples) * 100:.0f}%")

    # 注入样本
    inj_samples = [
        "SELECT * FROM orders; DROP TABLE users",
        "SELECT * FROM orders WHERE 1=1; DELETE FROM users",
        "SELECT * FROM orders INTO OUTFILE '/tmp/x'",
        "SELECT SLEEP(5) FROM orders",
        "DROP TABLE orders",
        "UPDATE orders SET status='done'",
        "DELETE FROM users",
        "SELECT BENCHMARK(10000000, MD5('x')) FROM orders",
        # 绕过样本：注释 / CTE / UNION 隐藏多语句写操作
        "SELECT * FROM orders /*x*/; DROP TABLE users",
        "WITH x AS (SELECT 1) SELECT * FROM x; DROP TABLE users",
        "SELECT * FROM orders UNION SELECT * FROM users; UPDATE users SET level='钻石'",
    ]
    blocked_inj = sum(1 for sql in inj_samples if not validate(sql, "analyst", rbac).ok)
    print(f"注入拦截率：{blocked_inj}/{len(inj_samples)} = {blocked_inj / len(inj_samples) * 100:.0f}%")


if __name__ == "__main__":
    run_accuracy()
    run_security()
