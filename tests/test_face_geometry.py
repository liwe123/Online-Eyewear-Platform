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
VALID_METHODS = {"geometric", "fallback_landmark", "fallback_box", "unknown"}


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
    # face_count：检出人脸时必含且为 >=1 的整数；未检出时可缺省
    if result["face_detected"]:
        assert "face_count" in result
        assert isinstance(result["face_count"], int) and result["face_count"] >= 1
    elif "face_count" in result:
        assert isinstance(result["face_count"], int) and result["face_count"] >= 1
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


def test_classify_40px_image_dimension_guard():
    """40x40（< MIN_IMAGE_SIZE=60）触发尺寸守卫：不识别且带 reason 说明。"""
    result = face_geometry.classify_face_shape(_black_image(width=40, height=40))
    _assert_result_structure(result)
    assert result["face_detected"] is False
    assert result["face_shape"] == ""
    assert result["method"] == "unknown"
    assert result.get("reason") == "图片尺寸过小，无法识别人脸"


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


def test_geometric_mid_t_zero_ratios_none(monkeypatch):
    """mid_t≈0（中庭不可测）时上庭/下庭比例应置 None，而非无意义数值。

    通过 monkeypatch 注入合成 FaceMesh 关键点走 geometric 路径
    （本环境未装 mediapipe，正常流程无法触发该分支）。
    """
    class _LM:
        __slots__ = ("x", "y")

        def __init__(self, x, y):
            self.x = x
            self.y = y

    lms = [_LM(0.5, 0.5) for _ in range(468)]
    # 关键点索引来自 face_geometry 模块常量；9(眉间) 与 2(鼻下) 重合 → mid_t≈0
    for i, (x, y) in {
        10: (0.5, 0.20), 152: (0.5, 0.90),
        234: (0.30, 0.70), 454: (0.70, 0.70),
        172: (0.25, 0.80), 397: (0.75, 0.80),
        103: (0.32, 0.30), 332: (0.68, 0.30),
        9: (0.50, 0.45), 2: (0.50, 0.45),
        168: (0.50, 0.40), 1: (0.50, 0.50),
        33: (0.40, 0.50), 133: (0.48, 0.50),
        362: (0.52, 0.50), 263: (0.60, 0.50),
        61: (0.42, 0.70), 291: (0.58, 0.70),
    }.items():
        lms[i] = _LM(x, y)

    class _FakeFace:
        def __init__(self, landmark):
            self.landmark = landmark

    class _FakeRes:
        def __init__(self):
            self.multi_face_landmarks = [_FakeFace(lms)]

    class _FakeMesh:
        def process(self, rgb):
            return _FakeRes()

    monkeypatch.setattr(face_geometry, "_get_face_mesh", lambda: _FakeMesh())
    result = face_geometry.classify_face_shape(_black_image(100, 100))
    assert result["face_detected"] is True
    assert result["face_count"] == 1
    assert result["face_shape"] != ""
    # 中庭不可测 → 比例置 None，而非产出无意义的像素比值
    assert result["metrics"]["upper_third_ratio"] is None
    assert result["metrics"]["lower_third_ratio"] is None
    assert result["metrics"]["face_ratio"] is not None


# ---------------------------------------------------------------------------
# 5 关键点兜底分类（fallback_landmark）
# ---------------------------------------------------------------------------

def _long_face_lm5():
    """长脸样例：检测框高宽比 1.4（>1.35 → 长方形）。"""
    box = (10.0, 20.0, 100.0, 140.0)
    lm5 = [
        (40.0, 60.0),  # 左眼
        (80.0, 60.0),  # 右眼
        (60.0, 85.0),  # 鼻
        (45.0, 100.0),  # 左嘴角
        (75.0, 100.0),  # 右嘴角
    ]
    return box, lm5


def test_classify_by_landmarks_direct():
    """纯函数：给定框 + 关键点，返回结构化结果与中文解释。"""
    box, lm5 = _long_face_lm5()
    shape, metrics, analysis, verdict = face_geometry._classify_by_landmarks(box, lm5)
    assert shape == "长方形"
    assert metrics["face_ratio"] == pytest.approx(1.4)
    assert metrics["mouth_ratio"] is not None
    assert metrics["face_to_eye_ratio"] is not None
    assert metrics["jaw_ratio"] is None  # 5 关键点无法刻画下颌
    assert len(analysis) == 3
    assert verdict


def test_classify_by_landmarks_round():
    """短圆脸：框高宽比 1.0 + 嘴宽比 0.4（≥0.28）→ 圆形。"""
    box = (0.0, 0.0, 100.0, 100.0)
    lm5 = [
        (38.0, 45.0), (62.0, 45.0), (50.0, 60.0),
        (30.0, 72.0), (70.0, 72.0),
    ]
    shape, metrics, _, _ = face_geometry._classify_by_landmarks(box, lm5)
    assert shape == "圆形"
    assert metrics["mouth_ratio"] == pytest.approx(0.4)


def test_classify_face_shape_fallback_landmark(monkeypatch):
    """检测框 + 5 关键点 → method=fallback_landmark，指标/解释完整。"""
    box, lm5 = _long_face_lm5()
    monkeypatch.setattr(face_geometry, "_detect_face", lambda img: (box, lm5))
    monkeypatch.setattr(face_geometry, "_get_face_mesh", lambda: None)
    monkeypatch.setattr(face_geometry, "_get_mtcnn", lambda: None)
    result = face_geometry.classify_face_shape(_black_image(160, 160))
    _assert_result_structure(result)
    assert result["face_detected"] is True
    assert result["method"] == "fallback_landmark"
    assert result["face_shape"] == "长方形"
    assert result["metrics"]["face_ratio"] == pytest.approx(1.4)
    assert result["analysis"] and result["verdict"]


def test_classify_face_shape_fallback_box_no_landmarks(monkeypatch):
    """仅检测框（无关键点）→ 维持 fallback_box。"""
    box, _ = _long_face_lm5()
    monkeypatch.setattr(face_geometry, "_detect_face", lambda img: (box, None))
    monkeypatch.setattr(face_geometry, "_get_face_mesh", lambda: None)
    monkeypatch.setattr(face_geometry, "_get_mtcnn", lambda: None)
    result = face_geometry.classify_face_shape(_black_image(160, 160))
    _assert_result_structure(result)
    assert result["face_detected"] is True
    assert result["method"] == "fallback_box"
    assert result["face_shape"] == "长方形"  # 框高宽比 1.4


def test_detect_face_graceful_when_all_detectors_unavailable(monkeypatch):
    """YuNet 与 MTCNN 均不可用、Haar 在纯黑图无检出 → _detect_face 返回 None。"""
    monkeypatch.setattr(face_geometry, "_get_yunet", lambda: None)
    monkeypatch.setattr(face_geometry, "_get_mtcnn", lambda: None)
    assert face_geometry._detect_face(_black_image(120, 120)) is None


def test_yunet_row_to_lm5_reorders_landmarks():
    """YuNet 输出 [.., 右眼,左眼,鼻,右嘴角,左嘴角,..] → 归一化为 [左眼,右眼,鼻,左嘴角,右嘴角]。

    防止关键点索引错位（最值得验证的新代码）。
    """
    row = np.array([
        100.0, 50.0, 200.0, 300.0,      # box (x, y, w, h)
        150.0, 100.0,                   # 右眼 (RE)
        250.0, 100.0,                   # 左眼 (LE)
        200.0, 180.0,                   # 鼻 (N)
        160.0, 220.0,                   # 右嘴角 (RM)
        240.0, 220.0,                   # 左嘴角 (LM)
        0.9,                            # score
    ])
    lm5 = face_geometry._yunet_row_to_lm5(row)
    assert lm5 == [
        (250.0, 100.0),  # 左眼（来自 f[6], f[7]）
        (150.0, 100.0),  # 右眼（来自 f[4], f[5]）
        (200.0, 180.0),  # 鼻
        (240.0, 220.0),  # 左嘴角（来自 f[12], f[13]）
        (160.0, 220.0),  # 右嘴角（来自 f[10], f[11]）
    ]
