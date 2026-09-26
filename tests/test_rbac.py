import pytest

from rbac import RBAC, PermissionDenied


def test_authorized_tables():
    rbac = RBAC()
    assert set(rbac.authorized_tables("analyst")) == {"orders", "users", "products"}
    assert rbac.authorized_tables("ops") == ["orders"]
    assert rbac.authorized_tables("guest") == []


def test_check_pass():
    rbac = RBAC()
    rbac.check("analyst", ["orders", "users"])  # 不抛异常


def test_check_denied():
    rbac = RBAC()
    with pytest.raises(PermissionDenied):
        rbac.check("ops", ["users"])
