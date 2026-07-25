# -*- coding: utf-8 -*-
"""face_geometry 模块测试。

不测真实人脸图片识别（无数据集），只验证：
- 模块可导入；
- is_mediapipe_available 返回 bool（本环境未装 mediapipe，应为 False）；
- 对全黑 / 噪声图片 classify_face_shape 不崩溃且返回结构完整；
- 对非法输入（None / 空数组 / 非 ndarray）安全降级。
"""
import cv2
import numpy as np
import pytest

import face_geometry

REQUIRED_KEYS = {"face_shape", "metrics", "face_detected", "method"}
METRIC_KEYS = {"face_ratio", "jaw_ratio", "forehead_ratio"}
VALID_METHODS = {"geometric", "fallback_box", "unknown"}


def _black_image(width=120, height=120):
    return np.zeros((height, width, 3), dtype=np.uint8)


def _noise_image(width=120, height=120, seed=42):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


def _assert_result_structure(result: dict) -> None:
    assert isinstance(result, dict)
    assert REQUIRED_KEYS.issubset(result.keys())
    assert isinstance(result["face_shape"], str)
    assert isinstance(result["face_detected"], bool)
    assert result["method"] in VALID_METHODS
    assert isinstance(result["metrics"], dict)
    assert METRIC_KEYS.issubset(result["metrics"].keys())
    # 一致性：未检出人脸时脸型应为空字符串
    if not result["face_detected"]:
        assert result["face_shape"] == ""
    else:
        assert result["face_shape"] != ""


def test_module_importable():
    assert callable(face_geometry.classify_face_shape)
    assert callable(face_geometry.is_mediapipe_available)
    # 阈值常量存在且为正数
    assert face_geometry.FACE_RATIO_LONG > 0
    assert face_geometry.FACE_RATIO_ROUND > 0


def test_is_mediapipe_available_returns_bool():
    available = face_geometry.is_mediapipe_available()
    assert isinstance(available, bool)
    # 本测试环境未安装 mediapipe，预期 False；若将来安装则允许 True


def test_classify_black_image_not_crash():
    result = face_geometry.classify_face_shape(_black_image())
    _assert_result_structure(result)
    # 纯黑图不可能检测到人脸
    assert result["face_detected"] is False
    assert result["face_shape"] == ""


def test_classify_noise_image_not_crash():
    result = face_geometry.classify_face_shape(_noise_image())
    _assert_result_structure(result)


def test_classify_small_image_not_crash():
    # 小于人脸检测最小尺寸的图也不应崩溃
    result = face_geometry.classify_face_shape(_black_image(width=30, height=30))
    _assert_result_structure(result)
    assert result["face_detected"] is False


@pytest.mark.parametrize("bad_input", [
    None,
    np.array([]),
    np.zeros((0, 0, 3), dtype=np.uint8),
    "not-an-image",
    12345,
], ids=["none", "empty_1d", "empty_3d", "string", "int"])
def test_classify_invalid_input_safe(bad_input):
    result = face_geometry.classify_face_shape(bad_input)
    _assert_result_structure(result)
    assert result["face_detected"] is False
    assert result["method"] == "unknown"
