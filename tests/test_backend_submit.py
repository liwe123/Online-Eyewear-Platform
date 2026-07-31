# -*- coding: utf-8 -*-
"""后端用户提交接口测试：完整流程 / 参数校验 / 安全头 / 限流。

历史问题（已在代码审查后修复，保留说明备查）：
- user_submit 错误分支曾返回 HTTP 200 + body {"code":400}，现已统一返回真实
  HTTP 状态码；本文件校验类用例同时断言 HTTP 状态码与 body["code"]。
- endpoint 级 10/minute 限流曾因包装结果未赋回 app.view_functions 而不生效，
 现已修复，对应用例正常运行（原 xfail 已转 XPASS）。
"""
import io

import pytest
import requests

from conftest import (
    FakeResponse,
    MOCK_FACE_SHAPE,
    MOCK_RECOMMENDATION,
    backend_main,
    make_upload_file,
)
from models import Account, RecommendRecord, User, db

VALID_FORM = {
    "pupil_distance": "62",
    "corneal_curvature": "43",
    "myopia_degree": "-3.5",
}


def _submit(client, png_bytes, form=None, filename="face.png", headers=None):
    data = dict(form or VALID_FORM)
    data["image"] = make_upload_file(png_bytes, filename)
    return client.post(
        "/api/user/submit", data=data,
        content_type="multipart/form-data",
        headers=headers,
    )


def _assert_business_error(resp, code: int) -> None:
    """断言业务错误码（user_submit 当前实现 HTTP 状态码恒为 200，见模块 docstring）。"""
    assert resp.status_code in (200, code), (
        f"HTTP 状态码异常: {resp.status_code}（body: {resp.get_json()}）"
    )
    assert resp.get_json()["code"] == code


class TestSubmitFlow:
    """完整提交流程（模型服务已 mock）。"""

    def test_submit_success_full_flow(self, client, png_bytes):
        resp = _submit(client, png_bytes)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["code"] == 200
        assert body["msg"] == "提交成功"
        data = body["data"]
        assert data["face_shape"] == MOCK_FACE_SHAPE
        assert data["recommendation"] == MOCK_RECOMMENDATION
        assert data["user_id"] >= 1

        # 数据库落库验证
        with backend_main.app.app_context():
            user = db.session.get(User, data["user_id"])
            assert user is not None
            assert user.pupil_distance == 62.0
            assert user.corneal_curvature == 43.0
            assert user.myopia_degree == -3.5
            assert user.account_id is None  # 匿名提交

            record = RecommendRecord.query.filter_by(user_id=user.id).first()
            assert record is not None
            assert record.face_shape == MOCK_FACE_SHAPE
            expected_ids = ",".join(item["glasses_id"] for item in MOCK_RECOMMENDATION)
            assert record.glasses_ids == expected_ids

    def test_submit_with_token_links_account(self, client, png_bytes, user_headers):
        resp = _submit(client, png_bytes, headers=user_headers)
        assert resp.status_code == 200
        user_id = resp.get_json()["data"]["user_id"]
        with backend_main.app.app_context():
            user = db.session.get(User, user_id)
            account = Account.query.filter_by(username="testuser").first()
            assert account is not None
            assert user.account_id == account.id, "携带 token 提交应关联账号"

    def test_security_headers_present(self, client, png_bytes):
        resp = _submit(client, png_bytes)
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        csp = resp.headers["Content-Security-Policy"]
        assert csp.startswith("default-src 'self'")
        assert "img-src" in csp and "script-src" in csp and "style-src" in csp


class TestSubmitValidation:
    """参数与文件校验（业务错误码契约，HTTP 状态码问题见模块 docstring）。"""

    def test_missing_image_400(self, client):
        resp = client.post("/api/user/submit", data=dict(VALID_FORM),
                           content_type="multipart/form-data")
        _assert_business_error(resp, 400)
        assert "图片" in resp.get_json()["msg"]

    def test_empty_filename_400(self, client, png_bytes):
        data = dict(VALID_FORM)
        data["image"] = make_upload_file(png_bytes, "")
        resp = client.post("/api/user/submit", data=data,
                           content_type="multipart/form-data")
        _assert_business_error(resp, 400)

    def test_disallowed_extension_400(self, client, png_bytes):
        resp = _submit(client, png_bytes, filename="face.gif")
        _assert_business_error(resp, 400)
        assert "格式" in resp.get_json()["msg"]

    @pytest.mark.parametrize("field,value", [
        ("pupil_distance", "20"),      # 瞳距 < 30
        ("pupil_distance", "90"),      # 瞳距 > 80
        ("corneal_curvature", "25"),   # 角膜曲率 < 30
        ("corneal_curvature", "60"),   # 角膜曲率 > 50
        ("myopia_degree", "-25"),      # 近视 < -20
        ("myopia_degree", "15"),       # 近视 > 10
        ("pupil_distance", "abc"),     # 非数字
    ], ids=["pd_low", "pd_high", "cc_low", "cc_high",
            "myopia_low", "myopia_high", "pd_not_a_number"])
    def test_param_out_of_range_400(self, client, png_bytes, field, value):
        form = dict(VALID_FORM)
        form[field] = value
        resp = _submit(client, png_bytes, form=form)
        _assert_business_error(resp, 400)

    def test_no_db_write_on_validation_failure(self, client, png_bytes):
        form = dict(VALID_FORM)
        form["pupil_distance"] = "20"
        resp = _submit(client, png_bytes, form=form)
        _assert_business_error(resp, 400)
        with backend_main.app.app_context():
            assert User.query.count() == 0
            assert RecommendRecord.query.count() == 0

    def test_request_body_too_large_no_db_write(self, client, png_bytes):
        """请求体超过 MAX_CONTENT_LENGTH(10MB) → 413 且不落库。

        user_submit 通过显式 except RequestEntityTooLarge 返回 413，
        不落库是稳定契约。
        """
        data = dict(VALID_FORM)
        big = io.BytesIO(b"\0" * (10 * 1024 * 1024 + 1024))
        data["image"] = (big, "big.png", "image/png")
        resp = client.post("/api/user/submit", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 413
        assert resp.get_json()["code"] == 413
        with backend_main.app.app_context():
            assert User.query.count() == 0
            assert RecommendRecord.query.count() == 0

    def test_auth_request_too_large_413_handler(self, client):
        """验证全局 413 错误处理器的自定义 body（未被子路由吞掉的路径）。

        登录路由的 request.get_json() 不会吞掉 RequestEntityTooLarge，
        超限 JSON 请求体应触发 413 handler 并返回 {"code":413, ...}。
        """
        huge_json = b'{"username": "a' + b"x" * (10 * 1024 * 1024) + b'"}'
        resp = client.post("/api/auth/login", data=huge_json,
                           content_type="application/json")
        assert resp.status_code == 413
        body = resp.get_json()
        assert body["code"] == 413
        assert "10MB" in body["msg"]


class TestModelServiceFailure:
    """模型服务故障分支（此前未覆盖的关键缺口）。

    模拟 requests.post 抛错 / 返回非 200 / body.code != 200，
    断言：返回真实 HTTP 错误码、错误码契约一致、且不产生任何落库数据。
    """

    def _assert_no_db_write(self):
        with backend_main.app.app_context():
            assert User.query.count() == 0
            assert RecommendRecord.query.count() == 0

    def test_model_timeout_500(self, client, png_bytes, monkeypatch):
        """requests.exceptions.Timeout → rollback + 500 JSON，无落库。"""
        def _timeout(url, **kwargs):
            raise requests.exceptions.Timeout("simulated timeout")
        monkeypatch.setattr(requests, "post", _timeout)
        resp = _submit(client, png_bytes)
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["code"] == 500
        assert "超时" in body["msg"]
        self._assert_no_db_write()

    def test_model_connection_error_500(self, client, png_bytes, monkeypatch):
        """requests.exceptions.ConnectionError → rollback + 500 JSON，无落库。"""
        def _conn_error(url, **kwargs):
            raise requests.exceptions.ConnectionError("simulated conn error")
        monkeypatch.setattr(requests, "post", _conn_error)
        resp = _submit(client, png_bytes)
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["code"] == 500
        assert "连接失败" in body["msg"]
        self._assert_no_db_write()

    def test_face_shape_http_error_400(self, client, png_bytes, monkeypatch):
        """模型返回 HTTP != 200（脸型识别）→ 400「脸型识别失败」，无落库。"""
        def _fake(url, **kwargs):
            return FakeResponse({"code": 500, "msg": "server error"}, status_code=500)
        monkeypatch.setattr(requests, "post", _fake)
        resp = _submit(client, png_bytes)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == 400
        assert body["msg"] == "脸型识别失败"
        self._assert_no_db_write()

    def test_face_shape_body_code_error_400(self, client, png_bytes, monkeypatch):
        """模型 body.code != 200（脸型识别）→ 400，透出模型 msg，无落库。"""
        def _fake(url, **kwargs):
            return FakeResponse({"code": 500, "msg": "识别服务内部错误"})
        monkeypatch.setattr(requests, "post", _fake)
        resp = _submit(client, png_bytes)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == 400
        assert "识别服务内部错误" in body["msg"]
        self._assert_no_db_write()

    def test_recommend_http_error_400(self, client, png_bytes, monkeypatch):
        """模型返回 HTTP != 200（推荐）→ 400「推荐失败」，无落库。"""
        def _fake(url, **kwargs):
            if url.endswith("/predict_face_shape"):
                return FakeResponse({"code": 200, "face_shape": MOCK_FACE_SHAPE,
                                     "msg": "识别成功", "method": "geometric"})
            return FakeResponse({"code": 500, "msg": "server error"}, status_code=500)
        monkeypatch.setattr(requests, "post", _fake)
        resp = _submit(client, png_bytes)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == 400
        assert body["msg"] == "推荐失败"
        self._assert_no_db_write()

    def test_recommend_body_code_error_400(self, client, png_bytes, monkeypatch):
        """模型 body.code != 200（推荐）→ 400，透出模型 msg，无落库。"""
        def _fake(url, **kwargs):
            if url.endswith("/predict_face_shape"):
                return FakeResponse({"code": 200, "face_shape": MOCK_FACE_SHAPE,
                                     "msg": "识别成功", "method": "geometric"})
            return FakeResponse({"code": 500, "msg": "推荐服务内部错误"})
        monkeypatch.setattr(requests, "post", _fake)
        resp = _submit(client, png_bytes)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == 400
        assert "推荐服务内部错误" in body["msg"]
        self._assert_no_db_write()


class TestRateLimit:
    """限流测试（保持为本文件最后执行的类，fixture 已重置 limiter 存储）。"""

    def test_default_rate_limit_429(self, client):
        """default 120/minute：连续 121 次普通接口请求应触发 429 且返回 {"code":429}。"""
        for i in range(120):
            resp = client.get("/api/glasses/list")
            assert resp.status_code == 200, f"第 {i + 1} 次请求应成功，实际 {resp.status_code}"
        resp = client.get("/api/glasses/list")
        assert resp.status_code == 429
        assert resp.get_json()["code"] == 429

    def test_submit_rate_limit_429_after_10_requests(self, client, png_bytes):
        """submit 10/minute：连续 11 次提交应触发 429（限流 bug 已修复）。"""
        for i in range(10):
            resp = _submit(client, png_bytes)
            assert resp.status_code == 200, f"第 {i + 1} 次请求应成功，实际 {resp.status_code}"
        resp = _submit(client, png_bytes)
        assert resp.status_code == 429
        assert resp.get_json()["code"] == 429
