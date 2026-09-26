from rbac import RBAC
from sql_validator import validate


def test_valid_select():
    r = validate("SELECT * FROM orders WHERE status='paid'", "analyst", RBAC())
    assert r.ok
    assert r.tables == ["orders"]


def test_readonly_reject():
    r = validate("UPDATE orders SET status='done'", "analyst", RBAC())
    assert not r.ok
    assert r.checks["readonly"] is False


def test_drop_reject():
    r = validate("DROP TABLE orders", "analyst", RBAC())
    assert not r.ok


def test_permission_denied():
    # ops 只能查 orders，查 users 越权
    r = validate("SELECT * FROM users", "ops", RBAC())
    assert not r.ok
    assert r.checks["permission"] is False


def test_multi_statement_reject():
    r = validate("SELECT * FROM orders; DROP TABLE users", "analyst", RBAC())
    assert not r.ok
    assert r.checks["syntax"] is False or r.checks["injection"] is False


def test_syntax_error():
    r = validate("SELEC * FROM orders", "analyst", RBAC())
    assert not r.ok
    assert r.checks["syntax"] is False


def test_join_extracts_both_tables():
    r = validate(
        "SELECT o.id, u.name FROM orders o JOIN users u ON o.user_id=u.id",
        "analyst", RBAC(),
    )
    assert r.ok
    assert set(r.tables) == {"orders", "users"}


def test_union_readonly():
    r = validate(
        "SELECT id FROM orders UNION SELECT id FROM users",
        "analyst", RBAC(),
    )
    assert r.ok
