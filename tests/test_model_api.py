# -*- coding: utf-8 -*-
"""model_api FastAPI 服务测试。

不运行 lifespan（避免读取真实 data/glasses_data.csv）：直接实例化 TestClient
（不进入 with 上下文即不触发 lifespan），并手动向 model_api._resources
注入测试用眼镜数据。
"""
import math

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

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

    def test_health_degraded_when_resources_missing(self, model_client):
        """资源未加载时 /health 应返回 status=degraded（区别于库存为 0 的 ok）。"""
        saved = dict(model_api._resources)
        try:
            model_api._resources.clear()
            resp = model_client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "degraded"
            assert body["glasses_count"] == 0
            assert "reason" in body
        finally:
            model_api._resources.clear()
            model_api._resources.update(saved)


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


class TestEyeDataValidation:
    """EyeData 生理范围 / 有限性校验。"""

    @pytest.mark.parametrize("field,value", [
        ("pupil_distance", 10.0),        # 瞳距过小
        ("pupil_distance", 200.0),       # 瞳距过大
        ("corneal_curvature", 20.0),     # 角膜曲率过小
        ("corneal_curvature", 200.0),    # 角膜曲率过大
        ("myopia_degree", -99999.0),     # 近视度数过小（屈光度）
        ("myopia_degree", 5000.0),       # 近视度数过大（正数度数）
    ], ids=["pd_too_small", "pd_too_large", "cc_too_small", "cc_too_large",
            "myopia_absurd_low", "myopia_absurd_high"])
    def test_out_of_range_eye_data_422(self, model_client, field, value):
        bad = dict(VALID_EYE_DATA, **{field: value})
        resp = model_client.post(
            "/get_recommendation", json=bad, params={"face_shape": "方形"},
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")],
                             ids=["nan", "pos_inf", "neg_inf"])
    def test_non_finite_eye_data_rejected(self, value):
        """NaN / 无穷大在模型层被拒绝。

        注：此处直接校验 pydantic 模型而非走 HTTP——422 错误响应本身会携带
        input 值，starlette 的 JSON 序列化器（allow_nan=False）无法渲染
        NaN 字段，导致 TestClient 抛出 ValueError。模型层的 ValidationError
        正是 HTTP 422 的根因。
        """
        with pytest.raises(ValidationError):
            model_api.EyeData(
                pupil_distance=value, corneal_curvature=43.0, myopia_degree=-3.5,
            )
        with pytest.raises(ValidationError):
            model_api.EyeData(
                pupil_distance=62.0, corneal_curvature=43.0, myopia_degree=value,
            )


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

    def test_predict_image_too_large_400(self, model_client):
        """图片字节超过 MAX_IMAGE_SIZE(10MB) → 业务错误码 400。"""
        big = b"\0" * (model_api.MAX_IMAGE_SIZE + 1)
        resp = model_client.post(
            "/predict_face_shape",
            files={"file": ("big.png", big, "image/png")},
        )
        assert resp.status_code == 200  # 业务错误码在 body，HTTP 仍为 200
        body = resp.json()
        assert body["code"] == 400
        assert "10MB" in body["msg"]
