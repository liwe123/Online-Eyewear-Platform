# -*- coding: utf-8 -*-
"""后端认证接口测试：注册 / 登录 / admin 初始化。"""
import pytest

from conftest import settings
from models import Account, db


class TestRegister:
    """POST /api/auth/register"""

    def test_register_success(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "alice01", "password": "pass123456",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["code"] == 200
        assert body["msg"] == "注册成功"
        assert body["data"]["user_id"] >= 1

    def test_register_duplicate_username_400(self, client):
        payload = {"username": "bob2024", "password": "pass123456"}
        first = client.post("/api/auth/register", json=payload)
        assert first.status_code == 200
        second = client.post("/api/auth/register", json=payload)
        assert second.status_code == 400
        body = second.get_json()
        assert body["code"] == 400
        assert "已存在" in body["msg"]

    @pytest.mark.parametrize("payload", [
        {"username": "ab", "password": "pass123456"},          # 用户名太短
        {"username": "x" * 21, "password": "pass123456"},      # 用户名太长
        {"username": "validname", "password": "12345"},        # 密码太短
        {"username": "validname", "password": "y" * 65},       # 密码太长
        {"username": "", "password": "pass123456"},            # 空用户名
        {},                                                    # 空 body
    ], ids=["username_too_short", "username_too_long", "password_too_short",
            "password_too_long", "empty_username", "empty_body"])
    def test_register_invalid_params_400(self, client, payload):
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == 400

    @pytest.mark.parametrize("payload", [
        {"username": None, "password": "pass123456"},  # null 用户名 → "" → 400
        {"username": "validname", "password": None},   # null 密码 → "" → 400
    ], ids=["username_null", "password_null"])
    def test_register_null_credentials_400(self, client, payload):
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == 400
        # 不应出现 str(None) 垃圾信息
        assert "None" not in body["msg"]


class TestLogin:
    """POST /api/auth/login"""

    def _register(self, client, username="carol01", password="pass123456"):
        resp = client.post("/api/auth/register", json={
            "username": username, "password": password,
        })
        assert resp.status_code == 200

    def test_login_success_returns_token(self, client):
        self._register(client)
        resp = client.post("/api/auth/login", json={
            "username": "carol01", "password": "pass123456",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["code"] == 200
        data = body["data"]
        assert data["token"], "应返回非空 token"
        assert data["username"] == "carol01"
        assert data["role"] == "user"

    def test_login_wrong_password_401(self, client):
        self._register(client)
        resp = client.post("/api/auth/login", json={
            "username": "carol01", "password": "wrong-password",
        })
        assert resp.status_code == 401
        assert resp.get_json()["code"] == 401

    def test_login_nonexistent_user_401(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "ghost999", "password": "pass123456",
        })
        assert resp.status_code == 401
        assert resp.get_json()["code"] == 401

    @pytest.mark.parametrize("payload", [
        {"username": "", "password": ""},                  # 空凭据
        {},                                                # 空 body
        {"username": "carol01", "password": None},         # null 密码
        {"username": None, "password": "pass123456"},      # null 用户名
    ], ids=["empty_credentials", "missing_body", "password_null", "username_null"])
    def test_login_empty_or_null_credentials_401(self, client, payload):
        """空 / 缺失 / null 凭据 → 401，不崩溃、无 str(None) 垃圾。"""
        self._register(client)
        resp = client.post("/api/auth/login", json=payload)
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["code"] == 401
        assert "None" not in body["msg"]


class TestTokenLifecycle:
    """token 校验与账号生命周期。"""

    def test_valid_token_account_deleted_401(self, client):
        """token 仍有效但账号已被删除 → 调用需认证接口返回 401 而非 403/200。"""
        from conftest import backend_main
        client.post("/api/auth/register", json={
            "username": "goner", "password": "pass123456",
        })
        login = client.post("/api/auth/login", json={
            "username": "goner", "password": "pass123456",
        })
        token = login.get_json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        # 从数据库中删除该账号（token 本身仍有效）
        with backend_main.app.app_context():
            acct = Account.query.filter_by(username="goner").first()
            assert acct is not None
            db.session.delete(acct)
            db.session.commit()
        resp = client.post("/api/admin/glasses", json={}, headers=headers)
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["code"] == 401
        assert "账号不存在" in body["msg"]


class TestAdminInit:
    """admin 账号初始化（fixture 建库时已调用 ensure_admin_account）。"""

    def test_admin_account_exists_after_init(self, client):
        from conftest import backend_main
        with backend_main.app.app_context():
            admin = Account.query.filter_by(role="admin").first()
            assert admin is not None, "初始化后应存在 admin 账号"
            assert admin.username == settings.ADMIN_USERNAME
            assert admin.check_password(settings.ADMIN_PASSWORD)

    def test_admin_can_login(self, client):
        resp = client.post("/api/auth/login", json={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["role"] == "admin"
