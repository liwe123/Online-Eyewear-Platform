"""几何脸型分类器。

基于 MediaPipe FaceMesh 的 468 个面部关键点计算三项比例指标，
再用透明规则将脸型分为：长方形 / 圆形 / 方形 / 鹅蛋脸。

指标定义（均以颧骨宽为基准做归一化）：
- face_ratio     = 脸长(发际线顶 10 号点 → 下巴 152 号点) / 颧骨宽(234 → 454)
- jaw_ratio      = 下颌宽(172 → 397) / 颧骨宽
- forehead_ratio = 额头宽(103 → 332) / 颧骨宽

降级策略（lazy + 容错）：
- mediapipe 可用   → method="geometric"，关键点几何分类；
- mediapipe 不可用 → method="fallback_box"，用 facenet-pytorch MTCNN
  （失败再退 OpenCV Haar）的人脸检测框长宽比做粗略分类；
- 两者皆不可用     → method="unknown"，face_detected=False（不随机猜测）。
"""
from __future__ import annotations

import math
from typing import Any, Optional

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# 模块级阈值常量（调参入口）
# ---------------------------------------------------------------------------
FACE_RATIO_LONG: float = 1.35        # face_ratio 大于该值 → 长方形
FACE_RATIO_ROUND: float = 1.15       # face_ratio 小于该值（且下颌宽达标）→ 圆形
JAW_RATIO_ROUND: float = 0.75        # 圆形判定的下颌宽比阈值
JAW_RATIO_SQUARE: float = 0.80       # 方形判定的下颌宽比阈值
FOREHEAD_JAW_MAX_DIFF: float = 0.08  # 方形判定：额头宽比与下颌宽比的最大允许差

# FaceMesh 关键点索引
_IDX_FOREHEAD_TOP: int = 10   # 发际线顶
_IDX_CHIN: int = 152          # 下巴尖
_IDX_CHEEK_L: int = 234       # 左颧骨
_IDX_CHEEK_R: int = 454       # 右颧骨
_IDX_JAW_L: int = 172         # 左下颌角
_IDX_JAW_R: int = 397         # 右下颌角
_IDX_FOREHEAD_L: int = 103    # 左额角
_IDX_FOREHEAD_R: int = 332    # 右额角
# 三庭五眼 / 鼻唇 参考点
_IDX_BROW_CENTER: int = 9      # 眉间点（前额正中）
_IDX_NOSE_ROOT: int = 168      # 鼻根（鼻梁起点）
_IDX_PHILTRUM: int = 2         # 鼻下点（鼻底中点）
_IDX_NOSE_TIP: int = 1         # 鼻尖
_IDX_EYE_OUT_L: int = 33       # 左眼外眦
_IDX_EYE_IN_L: int = 133       # 左眼内眦
_IDX_EYE_IN_R: int = 362       # 右眼内眦
_IDX_EYE_OUT_R: int = 263      # 右眼外眦
_IDX_MOUTH_L: int = 61         # 左嘴角
_IDX_MOUTH_R: int = 291        # 右嘴角

# 分析报告阈值（用于中文解释）
JAW_ANGLE_SQUARE: float = 115.0   # 下颌角 < 该值 → 方脸倾向（下颌轮廓硬朗）
JAW_ANGLE_OVAL: float = 130.0     # 下颌角 > 该值 → 尖下巴（鹅蛋/瓜子倾向）

# lazy 单例缓存
_face_mesh: Any = None
_mp_checked: bool = False
_mtcnn: Any = None
_mtcnn_checked: bool = False


def _get_face_mesh() -> Any:
    """lazy 初始化 MediaPipe FaceMesh；导入/初始化失败返回 None。

    返回:
        FaceMesh 实例或 None（mediapipe 不可用）。
    """
    global _face_mesh, _mp_checked
    if _face_mesh is not None:
        return _face_mesh
    if _mp_checked:
        return None
    _mp_checked = True
    try:
        import mediapipe as mp  # noqa: PLC0415 - 刻意 lazy 导入

        _face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
        )
    except Exception:
        _face_mesh = None
    return _face_mesh


def is_mediapipe_available() -> bool:
    """触发 lazy 导入并返回 mediapipe 是否可用（供健康检查使用）。

    返回:
        True 表示 geometric 路径可用。
    """
    return _get_face_mesh() is not None


def _get_mtcnn() -> Any:
    """lazy 初始化 facenet-pytorch MTCNN；失败返回 None。

    返回:
        MTCNN 实例或 None。
    """
    global _mtcnn, _mtcnn_checked
    if _mtcnn is not None:
        return _mtcnn
    if _mtcnn_checked:
        return None
    _mtcnn_checked = True
    try:
        from facenet_pytorch import MTCNN  # noqa: PLC0415 - 刻意 lazy 导入

        _mtcnn = MTCNN(keep_all=False, post_process=False, device="cpu")
    except Exception:
        _mtcnn = None
    return _mtcnn


def _classify_by_metrics(face_ratio: float, jaw_ratio: float, forehead_ratio: float) -> str:
    """按三项指标执行规则分类。

    参数:
        face_ratio: 脸长 / 颧骨宽。
        jaw_ratio: 下颌宽 / 颧骨宽。
        forehead_ratio: 额头宽 / 颧骨宽。

    返回:
        中文脸型标签：长方形 / 圆形 / 方形 / 鹅蛋脸。

    边界说明: face_ratio < FACE_RATIO_ROUND 但下颌偏窄（jaw_ratio 不达标）
    属于规则未覆盖的缝隙情形，短脸配窄下颌视觉上更接近鹅蛋脸而非圆形，
    故归入鹅蛋脸。
    """
    if face_ratio > FACE_RATIO_LONG:
        return "长方形"
    if face_ratio < FACE_RATIO_ROUND:
        return "圆形" if jaw_ratio > JAW_RATIO_ROUND else "鹅蛋脸"
    # FACE_RATIO_ROUND <= face_ratio <= FACE_RATIO_LONG
    if jaw_ratio >= JAW_RATIO_SQUARE and abs(forehead_ratio - jaw_ratio) < FOREHEAD_JAW_MAX_DIFF:
        return "方形"
    return "鹅蛋脸"


def _angle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    """计算 ∠abc（顶点 b）的角度，单位：度。用于下颌角近似。"""
    import numpy as _np  # 复用已导入的 np 亦可，这里局部引用避免作用域歧义

    ba = _np.array([a[0] - b[0], a[1] - b[1]])
    bc = _np.array([c[0] - b[0], c[1] - b[1]])
    norm_ba = float(_np.linalg.norm(ba))
    norm_bc = float(_np.linalg.norm(bc))
    if norm_ba < 1e-6 or norm_bc < 1e-6:
        return 0.0
    cosv = float(_np.clip(_np.dot(ba, bc) / (norm_ba * norm_bc), -1.0, 1.0))
    return math.degrees(math.acos(cosv))


def _explain_verdict(
    face_ratio: float, jaw_ratio: float, forehead_ratio: float, face_shape: str
) -> str:
    """生成脸型判定的中文依据文字。"""
    if face_shape == "长方形":
        rule = f"脸长宽比 {face_ratio:.2f} > {FACE_RATIO_LONG}（长脸特征）"
    elif face_shape == "圆形":
        rule = (
            f"脸长宽比 {face_ratio:.2f} < {FACE_RATIO_ROUND} 且 "
            f"下颌宽比 {jaw_ratio:.2f} > {JAW_RATIO_ROUND}（短圆脸、下颌饱满）"
        )
    elif face_shape == "方形":
        rule = (
            f"下颌宽比 {jaw_ratio:.2f} ≥ {JAW_RATIO_SQUARE} 且 "
            f"额宽比与下颌宽比差 {abs(forehead_ratio - jaw_ratio):.2f} < {FOREHEAD_JAW_MAX_DIFF}"
            f"（方正下颌、上下同宽）"
        )
    else:  # 鹅蛋脸 / 椭圆
        rule = (
            f"脸长宽比 {face_ratio:.2f} 适中，且下颌/额宽比例不符合方脸或圆脸特征"
            f"（轮廓柔和、下巴微尖）"
        )
    return f"判定为「{face_shape}」：{rule}。"


def _build_analysis(m: dict) -> list[dict]:
    """根据测量指标生成中文分析报告列表（每个指标配数值与解释）。"""
    fa = m.get("face_ratio") or 0.0
    jr = m.get("jaw_ratio") or 0.0
    fr = m.get("forehead_ratio") or 0.0
    ja = m.get("jaw_angle_deg") or 0.0
    ur = m.get("upper_third_ratio") or 0.0
    lr = m.get("lower_third_ratio") or 0.0
    fe = m.get("face_to_eye_ratio") or 0.0

    def _face_len_desc(v: float) -> str:
        if v > FACE_RATIO_LONG:
            return "脸偏长，适合横向扩张感、框高适中的镜框"
        if v < FACE_RATIO_ROUND:
            return "脸偏短圆，适合有高度、能拉长脸型的镜框"
        return "脸长比例均衡，多数镜框都较协调"

    def _jaw_desc(v: float) -> str:
        if v >= JAW_RATIO_SQUARE:
            return "下颌较宽，方脸感强，宜用圆润框型中和硬朗"
        if v < JAW_RATIO_ROUND:
            return "下颌偏窄，下巴线条柔和，鹅蛋/瓜子脸特征"
        return "下颌宽度适中"

    def _jaw_angle_desc(v: float) -> str:
        if v == 0.0:
            return "下颌轮廓角"
        if v < JAW_ANGLE_SQUARE:
            return "下颌角偏小，轮廓硬朗（方脸倾向）"
        if v > JAW_ANGLE_OVAL:
            return "下颌角偏大，下巴尖翘（鹅蛋/瓜子脸倾向）"
        return "下颌角适中"

    def _third_desc(v: float, name: str) -> str:
        if v == 0.0:
            return f"{name}比例"
        if abs(v - 1.0) <= 0.15:
            return f"{name}≈1，三庭较均匀"
        if v > 1.15:
            return f"{name}偏大，该段偏长"
        return f"{name}偏小，该段偏短"

    return [
        {"label": "脸长宽比", "value": f"{fa:.2f}", "desc": _face_len_desc(fa)},
        {"label": "下颌宽比", "value": f"{jr:.2f}", "desc": _jaw_desc(jr)},
        {"label": "额宽比", "value": f"{fr:.2f}", "desc": "额头宽度与颧骨宽之比，影响上半脸视觉重量"},
        {"label": "下颌角", "value": f"{ja:.0f}°" if ja else "—", "desc": _jaw_angle_desc(ja)},
        {"label": "上庭/中庭", "value": f"{ur:.2f}" if ur else "—", "desc": _third_desc(ur, "上庭")},
        {"label": "下庭/中庭", "value": f"{lr:.2f}" if lr else "—", "desc": _third_desc(lr, "下庭")},
        {"label": "脸宽/眼宽", "value": f"{fe:.1f}" if fe else "—", "desc": "颧骨宽与单眼宽之比，越接近 5 越符合「三庭五眼」标准"},
    ]


def _classify_by_box(box_ratio: float) -> str:
    """用检测框长宽比做粗略分类（fallback 启发式）。

    参数:
        box_ratio: 人脸检测框高 / 宽。

    返回:
        中文脸型标签（检测框无法刻画下颌/额头，中间档统一归鹅蛋脸）。
    """
    if box_ratio > FACE_RATIO_LONG:
        return "长方形"
    if box_ratio < FACE_RATIO_ROUND:
        return "圆形"
    return "鹅蛋脸"


def _detect_face_box(image_bgr: np.ndarray) -> Optional[tuple[float, float, float, float]]:
    """检测人脸框，优先 MTCNN，失败后退 OpenCV Haar。

    参数:
        image_bgr: BGR 格式图像。

    返回:
        (x, y, w, h) 像素坐标；未检测到或检测器均不可用返回 None。
    """
    mtcnn = _get_mtcnn()
    if mtcnn is not None:
        try:
            from PIL import Image  # noqa: PLC0415 - 刻意 lazy 导入

            rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            boxes, _ = mtcnn.detect(Image.fromarray(rgb))
            if boxes is not None and len(boxes) > 0:
                x1, y1, x2, y2 = (float(v) for v in boxes[0])
                if x2 > x1 and y2 > y1:
                    return x1, y1, x2 - x1, y2 - y1
        except Exception:
            pass
    try:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda b: int(b[2]) * int(b[3]))
            return float(x), float(y), float(w), float(h)
    except Exception:
        pass
    return None


def classify_face_shape(image_bgr: np.ndarray) -> dict:
    """对 BGR 图像进行脸型分类。

    参数:
        image_bgr: OpenCV 解码的 BGR 图像（np.ndarray，HWC，uint8）。

    返回:
        dict，字段：
        - face_shape: str，中文脸型标签；未检测到人脸时为空字符串。
        - metrics: dict，face_ratio / jaw_ratio / forehead_ratio
          （保留 3 位小数；未检测到人脸时为 None）。
        - face_detected: bool。
        - method: "geometric" / "fallback_box" / "unknown"。
    """
    result: dict = {
        "face_shape": "",
        "metrics": {
            "face_ratio": None,
            "jaw_ratio": None,
            "forehead_ratio": None,
            "jaw_angle_deg": None,
            "upper_third_ratio": None,
            "lower_third_ratio": None,
            "face_to_eye_ratio": None,
            "mouth_ratio": None,
            "nose_ratio": None,
        },
        "landmarks_count": 0,
        "landmarks": [],
        "analysis": [],
        "verdict": "",
        "face_detected": False,
        "method": "unknown",
    }
    if image_bgr is None or not isinstance(image_bgr, np.ndarray) or image_bgr.size == 0:
        return result

    mesh = _get_face_mesh()
    box_detectors_ready = _get_mtcnn() is not None or cv2.data.haarcascades is not None
    if mesh is not None:
        result["method"] = "geometric"
        try:
            h, w = image_bgr.shape[:2]
            rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            res = mesh.process(rgb)
            if res.multi_face_landmarks:
                lms = res.multi_face_landmarks[0].landmark

                def _pt(i: int) -> tuple[float, float]:
                    return lms[i].x * w, lms[i].y * h

                def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
                    return math.hypot(a[0] - b[0], a[1] - b[1])

                face_len = _dist(_pt(_IDX_FOREHEAD_TOP), _pt(_IDX_CHIN))
                cheek_w = _dist(_pt(_IDX_CHEEK_L), _pt(_IDX_CHEEK_R))
                jaw_w = _dist(_pt(_IDX_JAW_L), _pt(_IDX_JAW_R))
                forehead_w = _dist(_pt(_IDX_FOREHEAD_L), _pt(_IDX_FOREHEAD_R))
                # 三庭五眼 / 鼻唇
                upper_t = _dist(_pt(_IDX_FOREHEAD_TOP), _pt(_IDX_BROW_CENTER))
                mid_t = _dist(_pt(_IDX_BROW_CENTER), _pt(_IDX_PHILTRUM))
                lower_t = _dist(_pt(_IDX_PHILTRUM), _pt(_IDX_CHIN))
                eye_w = _dist(_pt(_IDX_EYE_OUT_L), _pt(_IDX_EYE_IN_L))
                eye_gap = _dist(_pt(_IDX_EYE_IN_L), _pt(_IDX_EYE_IN_R))
                nose_len = _dist(_pt(_IDX_NOSE_ROOT), _pt(_IDX_PHILTRUM))
                mouth_w = _dist(_pt(_IDX_MOUTH_L), _pt(_IDX_MOUTH_R))
                # 下颌角：左颧弓外侧(234) - 左下颌角(172) - 下巴尖(152)
                jaw_angle = _angle(
                    _pt(_IDX_CHEEK_L), _pt(_IDX_JAW_L), _pt(_IDX_CHIN)
                )
                if cheek_w > 1e-6:
                    face_ratio = face_len / cheek_w
                    jaw_ratio = jaw_w / cheek_w
                    forehead_ratio = forehead_w / cheek_w
                    mid_safe = mid_t if mid_t > 1e-6 else 1.0
                    metrics: dict = {
                        "face_ratio": round(face_ratio, 3),
                        "jaw_ratio": round(jaw_ratio, 3),
                        "forehead_ratio": round(forehead_ratio, 3),
                        "jaw_angle_deg": round(jaw_angle, 1),
                        "upper_third_ratio": round(upper_t / mid_safe, 3),
                        "lower_third_ratio": round(lower_t / mid_safe, 3),
                        "face_to_eye_ratio": round(cheek_w / eye_w, 2) if eye_w > 1e-6 else None,
                        "mouth_ratio": round(mouth_w / cheek_w, 3),
                        "nose_ratio": round(nose_len / cheek_w, 3),
                    }
                    face_shape = _classify_by_metrics(face_ratio, jaw_ratio, forehead_ratio)
                    # 归一化关键点（前端点云可视化用）
                    landmarks = [[round(lm.x, 4), round(lm.y, 4)] for lm in lms]
                    result["metrics"] = metrics
                    result["landmarks_count"] = len(lms)
                    result["landmarks"] = landmarks
                    result["analysis"] = _build_analysis(metrics)
                    result["verdict"] = _explain_verdict(face_ratio, jaw_ratio, forehead_ratio, face_shape)
                    result["face_shape"] = face_shape
                    result["face_detected"] = True
                    return result
        except Exception:
            # 关键点提取异常时继续走检测框兜底
            pass
    elif box_detectors_ready:
        result["method"] = "fallback_box"

    # 兜底：mediapipe 不可用或未检出人脸时，用检测框长宽比粗略分类
    if result["method"] != "unknown":
        box = _detect_face_box(image_bgr)
        if box is not None:
            _, _, bw, bh = box
            if bw > 1e-6:
                result["face_shape"] = _classify_by_box(bh / bw)
                result["face_detected"] = True
                result["method"] = "fallback_box"
    return result
