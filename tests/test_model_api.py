# -*- coding: utf-8 -*-
"""model_api FastAPI 服务测试。

不运行 lifespan（避免读取真实 data/glasses_data.csv）：直接实例化 TestClient
（不进入 with 上下文即不触发 lifespan），并手动向 model_api._resources
注入测试用眼镜数据。
"""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import model_api
from conftest import make_png_bytes

ROWS = [
    ("R001", "圆形",   "50-20-140", "TR90",     -8.0,  0.0,  1.74, 399.0),
    ("R002", "圆形",   "52-18-140", "金属",      -4.0,  0.0,  1.56, 299.0),
    ("R003", "圆形",   "48-18-138", "复合板材",   -6.0, -1.0,  1.60, 499.0),
    ("R004", "方形",   "54-16-140", "TR90",      -6.0,  0.0,  1.56, 199.0),
    ("R005", "方形",   "52-18-142", "金属",      -2.0,  0.0,  1.50, 159.0),
    ("R006", "长方形", "56-16-144", "纯钛",      -8.0, -0.25, 1.67, 899.0),
    ("R007", "长方形", "55-17-140", "TR90",      -6.0,  0.0,  1.60, 349.0),
    ("R008", "猫眼形", "51-21-139", "复合板材",   -8.0, -0.5,  1.74, 519.0),
    ("R009", "多边形", "50-19-140", "金属",      -6.0,  0.0,  1.60, 459.0),
    ("R010", "鹅蛋形", "52-18-140", "TR90",      -4.0,  0.0,  1.56, 259.0),
    ("R011", "圆形",   "50-20-140", "TR90",     -10.0, -6.0,  1.74, 699.0),
    ("R012", "方形",   "53-17-141", "金属",      -0.5,  2.0,  1.50, 129.0),
]
COLUMNS = ["glasses_id", "frame_shape", "frame_size", "frame_material",
           "lens_degree_min", "lens_degree_max", "lens_refractive_index", "price"]

VALID_EYE_DATA = {
    "pupil_distance": 62.0,
    "corneal_curvature": 43.0,
    "myopia_degree": -3.5,
}


@pytest.fixture(scope="module")
def model_client():
    """绕过 lifespan 的 TestClient：手动注入测试眼镜数据。"""
    df = pd.DataFrame(ROWS, columns=COLUMNS)
    model_api._resources.clear()
    model_api._resources.update({
        "glasses_df": df,
        "glasses_by_shape": {shape: group for shape, group in df.groupby("frame_shape")},
        "all_shapes": list(df["frame_shape"].unique()),
    })
    # 不进入 with 上下文 → 不触发 lifespan，不会读取真实 CSV
    return TestClient(model_api.app)


class TestHealth:
    def test_health_ok(self, model_client):
        resp = model_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert isinstance(body["mediapipe"], bool)
        assert body["glasses_count"] == len(ROWS)


class TestGetRecommendation:
    def test_recommendation_success(self, model_client):
        resp = model_client.post(
            "/get_recommendation",
            json=VALID_EYE_DATA,
            params={"face_shape": "方形"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["msg"] == "推荐成功"
        recommendation = body["recommendation"]
        assert isinstance(recommendation, list)
        assert 1 <= len(recommendation) <= 3
        for item in recommendation:
            assert "glasses_id" in item
            assert "frame_shape" in item
            assert "price" in item
        assert isinstance(body["rules"], list) and len(body["rules"]) >= 1

    def test_recommendation_missing_body_field_422(self, model_client):
        bad = dict(VALID_EYE_DATA)
        del bad["myopia_degree"]
        resp = model_client.post(
            "/get_recommendation", json=bad, params={"face_shape": "方形"},
        )
        assert resp.status_code == 422

    def test_recommendation_invalid_field_type_422(self, model_client):
        bad = dict(VALID_EYE_DATA, myopia_degree="abc")
        resp = model_client.post(
            "/get_recommendation", json=bad, params={"face_shape": "方形"},
        )
        assert resp.status_code == 422

    def test_recommendation_missing_face_shape_422(self, model_client):
        resp = model_client.post("/get_recommendation", json=VALID_EYE_DATA)
        assert resp.status_code == 422

    def test_recommendation_no_stock_match_falls_back(self, model_client):
        resp = model_client.post(
            "/get_recommendation",
            json=dict(VALID_EYE_DATA, myopia_degree=-20.0),
            params={"face_shape": "方形"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        # 库存无完全匹配度数时，规则引擎自动放宽，按脸型/瞳距 fallback 推荐，避免空结果
        assert len(body["recommendation"]) == 3
        assert any("放宽" in r for r in body["rules"])


class TestPredictFaceShape:
    def test_predict_with_valid_image(self, model_client):
        png = make_png_bytes()
        resp = model_client.post(
            "/predict_face_shape",
            files={"file": ("face.png", png, "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["face_shape"], "应返回非空脸型（未检出人脸时返回默认脸型）"
        assert "method" in body

    def test_predict_with_invalid_bytes_400(self, model_client):
        resp = model_client.post(
            "/predict_face_shape",
            files={"file": ("bad.png", b"this-is-not-an-image", "image/png")},
        )
        # 接口约定：业务错误码在 body 中，HTTP 状态仍为 200
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 400
        assert "解码失败" in body["msg"]

    def test_predict_missing_file_422(self, model_client):
        resp = model_client.post("/predict_face_shape")
        assert resp.status_code == 422
