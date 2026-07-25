# -*- coding: utf-8 -*-
"""pytest 全局配置。

职责：
1. sys.path 注入项目根与 backend/（backend 模块以 flat 方式导入，与
   ``python backend/backend_main.py`` 运行方式一致）；
2. 导入 backend_main 之前把 DATABASE_URL 指向临时 sqlite 文件，避免触碰真实 data/backend.db；
3. 每个用例重建数据库、重置 flask-limiter 内存存储（防止跨用例残留导致意外 429）、
   并 monkeypatch 掉后端对模型服务的 requests.post 调用。
"""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# ---------- 1. 路径注入（须在导入项目模块之前） ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
for _p in (str(PROJECT_ROOT), str(BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# 处理后 sys.path[0] == backend/，sys.path[1] == 项目根

# ---------- 2. 测试专用配置（须在导入 backend 模块之前设置环境变量） ----------
_TEST_TMP = Path(tempfile.mkdtemp(prefix="dzy_pytest_"))
os.environ["BACKEND_DATABASE_URL"] = f"sqlite:///{(_TEST_TMP / 'test.db').as_posix()}"
os.environ["BACKEND_LOG_LEVEL"] = "WARNING"

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402

import backend_main  # noqa: E402
from auth import ensure_admin_account  # noqa: E402
from models import Account, Glasses, RecommendRecord, User, db  # noqa: E402
from settings import settings  # noqa: E402

# ---------- 3. 测试用眼镜数据（12 条，覆盖多种形状/材质/价格/度数范围） ----------
TEST_GLASSES = [
    dict(glasses_id="T001", frame_shape="圆形", frame_size="50-20-140", frame_material="TR90",
         lens_degree_min=-6.0, lens_degree_max=0.0, lens_refractive_index=1.60, price=399.0,
         image_url="/static/glasses/T001.svg"),
    dict(glasses_id="T002", frame_shape="圆形", frame_size="52-18-140", frame_material="金属",
         lens_degree_min=-4.0, lens_degree_max=0.0, lens_refractive_index=1.56, price=299.0,
         image_url="/static/glasses/T002.svg"),
    dict(glasses_id="T003", frame_shape="圆形", frame_size="48-18-138", frame_material="复合板材",
         lens_degree_min=-6.0, lens_degree_max=-1.0, lens_refractive_index=1.60, price=499.0,
         image_url="/static/glasses/T003.svg"),
    dict(glasses_id="T004", frame_shape="方形", frame_size="54-16-140", frame_material="TR90",
         lens_degree_min=-6.0, lens_degree_max=0.0, lens_refractive_index=1.56, price=199.0,
         image_url="/static/glasses/T004.svg"),
    dict(glasses_id="T005", frame_shape="方形", frame_size="52-18-142", frame_material="金属",
         lens_degree_min=-2.0, lens_degree_max=0.0, lens_refractive_index=1.50, price=159.0,
         image_url="/static/glasses/T005.svg"),
    dict(glasses_id="T006", frame_shape="长方形", frame_size="56-16-144", frame_material="纯钛",
         lens_degree_min=-8.0, lens_degree_max=-0.25, lens_refractive_index=1.67, price=899.0,
         image_url="/static/glasses/T006.svg"),
    dict(glasses_id="T007", frame_shape="长方形", frame_size="55-17-140", frame_material="TR90",
         lens_degree_min=-6.0, lens_degree_max=0.0, lens_refractive_index=1.60, price=349.0,
         image_url="/static/glasses/T007.svg"),
    dict(glasses_id="T008", frame_shape="猫眼形", frame_size="51-21-139", frame_material="复合板材",
         lens_degree_min=-8.0, lens_degree_max=-0.5, lens_refractive_index=1.74, price=519.0,
         image_url="/static/glasses/T008.svg"),
    dict(glasses_id="T009", frame_shape="多边形", frame_size="50-19-140", frame_material="金属",
         lens_degree_min=-6.0, lens_degree_max=0.0, lens_refractive_index=1.60, price=459.0,
         image_url="/static/glasses/T009.svg"),
    dict(glasses_id="T010", frame_shape="鹅蛋形", frame_size="52-18-140", frame_material="TR90",
         lens_degree_min=-4.0, lens_degree_max=0.0, lens_refractive_index=1.56, price=259.0,
         image_url="/static/glasses/T010.svg"),
    dict(glasses_id="T011", frame_shape="方形", frame_size="53-17-141", frame_material="纯钛",
         lens_degree_min=-8.0, lens_degree_max=-6.0, lens_refractive_index=1.74, price=1299.0,
         image_url="/static/glasses/T011.svg"),
    dict(glasses_id="T012", frame_shape="鹅蛋形", frame_size="50-18-138", frame_material="金属",
         lens_degree_min=-0.5, lens_degree_max=2.0, lens_refractive_index=1.50, price=129.0,
         image_url="/static/glasses/T012.svg"),
]

# ---------- 4. 模型服务 mock ----------
MOCK_FACE_SHAPE = "方形"
MOCK_RECOMMENDATION = [
    {"glasses_id": "T001", "frame_shape": "圆形", "frame_size": "50-20-140",
     "frame_material": "TR90", "lens_refractive_index": 1.60, "price": 399.0,
     "image_url": "/static/glasses/T001.svg"},
    {"glasses_id": "T002", "frame_shape": "圆形", "frame_size": "52-18-140",
     "frame_material": "金属", "lens_refractive_index": 1.56, "price": 299.0,
     "image_url": "/static/glasses/T002.svg"},
    {"glasses_id": "T010", "frame_shape": "鹅蛋形", "frame_size": "52-18-140",
     "frame_material": "TR90", "lens_refractive_index": 1.56, "price": 259.0,
     "image_url": "/static/glasses/T010.svg"},
]
MOCK_RULES = ["度数适配：硬过滤", "方形脸推荐圆形/鹅蛋形/猫眼形镜框"]


class FakeResponse:
    """模拟 requests.Response，提供后端用到的最小接口。"""

    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)
        self.content = self.text.encode("utf-8")

    def json(self) -> dict:
        return self._payload


def fake_model_post(url: str, **kwargs) -> FakeResponse:
    """按 URL 分发模型服务 mock 响应（脸型识别固定返回「方形」）。"""
    if url.endswith("/predict_face_shape"):
        return FakeResponse({
            "code": 200, "face_shape": MOCK_FACE_SHAPE,
            "msg": "识别成功", "method": "geometric",
        })
    if url.endswith("/get_recommendation"):
        return FakeResponse({
            "code": 200, "recommendation": MOCK_RECOMMENDATION,
            "msg": "推荐成功", "rules": MOCK_RULES,
        })
    raise AssertionError(f"未预期的模型服务请求: {url}")


# ---------- 5. 工具函数 ----------
def make_png_bytes(color=(0, 0, 0), width: int = 120, height: int = 120) -> bytes:
    """生成一张纯色 PNG 图片字节（用于提交/上传接口测试）。"""
    img = np.full((height, width, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok, "PNG 编码失败"
    return buf.tobytes()


def make_upload_file(content: bytes, filename: str = "face.png", content_type: str = "image/png"):
    """构造 Flask test_client 使用的 multipart 文件元组。"""
    return (io.BytesIO(content), filename, content_type)


def _reset_limiter() -> None:
    """重置 flask-limiter 的内存存储，避免跨用例残留触发意外 429。"""
    limiter = backend_main.limiter
    try:
        limiter.reset()
        return
    except Exception:
        pass
    try:
        limiter.storage.reset()
    except Exception:
        pass


# ---------- 6. fixtures ----------
@pytest.fixture()
def client(monkeypatch):
    """Flask 测试客户端：独立数据库 + 限流重置 + 模型服务 mock。"""
    app = backend_main.app
    _reset_limiter()
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()
        for row in TEST_GLASSES:
            db.session.add(Glasses(**row))
        db.session.commit()
        ensure_admin_account()
    monkeypatch.setattr(requests, "post", fake_model_post)
    with app.test_client() as test_client:
        yield test_client
    _reset_limiter()


@pytest.fixture()
def png_bytes() -> bytes:
    """一张全黑 PNG 图片字节。"""
    return make_png_bytes()


@pytest.fixture()
def admin_headers(client):
    """admin 账号登录后的认证头。"""
    resp = client.post("/api/auth/login", json={
        "username": settings.ADMIN_USERNAME,
        "password": settings.ADMIN_PASSWORD,
    })
    assert resp.status_code == 200, f"admin 登录失败: {resp.get_json()}"
    token = resp.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def user_headers(client):
    """注册并登录一个普通用户，返回认证头。"""
    resp = client.post("/api/auth/register", json={
        "username": "testuser", "password": "user123456",
    })
    assert resp.status_code == 200, f"注册失败: {resp.get_json()}"
    resp = client.post("/api/auth/login", json={
        "username": "testuser", "password": "user123456",
    })
    assert resp.status_code == 200, f"登录失败: {resp.get_json()}"
    token = resp.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
