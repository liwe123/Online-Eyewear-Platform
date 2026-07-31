"""几何脸型分类器。

基于 MediaPipe FaceMesh 的 468 个面部关键点计算三项比例指标，
再用透明规则将脸型分为：长方形 / 圆形 / 方形 / 鹅蛋脸。

指标定义（均以颧骨宽为基准做归一化）：
- face_ratio     = 脸长(发际线顶 10 号点 → 下巴 152 号点) / 颧骨宽(234 → 454)
- jaw_ratio      = 下颌宽(172 → 397) / 颧骨宽
- forehead_ratio = 额头宽(103 → 332) / 颧骨宽

降级策略（lazy + 容错）：
- mediapipe 可用   → method="geometric"，关键点几何分类；
- mediapipe 不可用 → method="fallback_landmark"，用 YuNet/MTCNN 的 5 个关键点
  （眼/鼻/嘴）做比例分类；仅检测框可用（Haar）→ method="fallback_box"；
- 两者皆不可用     → method="unknown"，face_detected=False（不随机猜测）。

mediapipe 中文路径兼容：若 site-packages 含非 ASCII（Windows C++ 层无法解析），
自动在系统盘建 ASCII junction 指向 site-packages 后重试导入（见 _ensure_mediapipe_ascii）。
"""
from __future__ import annotations

import math
import os
import shutil
import site
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
from loguru import logger

# ---------------------------------------------------------------------------
# 模块级阈值常量（调参入口）
# ---------------------------------------------------------------------------
MIN_IMAGE_SIZE: int = 60            # 小于该尺寸（任一边）的图无法可靠识别人脸
MAX_IMAGE_AREA: int = 4096 * 4096   # 超大面积先降采样再处理（约 16MP）
MAX_NUM_FACES: int = 5              # 允许检测的最多人数（用于统计并取主脸）
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

# 5 关键点兜底分类阈值（调参入口）
LM_FACE_RATIO_LONG: float = 1.35     # face_ratio > 该值 → 长方形（与 FACE_RATIO_LONG 一致）
LM_FACE_RATIO_ROUND: float = 1.15    # face_ratio < 该值 → 圆形/鹅蛋脸分界
LM_MOUTH_RATIO_FULL: float = 0.30    # 嘴宽/脸宽 ≥ 该值 → 下颌饱满（圆/方倾向）
LM_MOUTH_RATIO_ROUND: float = 0.28   # 圆脸判定的嘴宽比下限
LM_EYE_RATIO_WIDE: float = 5.0       # 脸宽/眼距 ≥ 该值 → 脸相对宽（五眼偏宽）

# YuNet 人脸检测模型（OpenCV DNN，~230KB，首次使用自动下载到 model/ 目录）
MODEL_DIR: Path = Path(__file__).resolve().parent / "model"
YUNET_MODEL_PATH: Path = MODEL_DIR / "yunet_face_detection.onnx"
YUNET_MODEL_URL: str = (
    # opencv_zoo 的模型文件走 Git LFS，raw.githubusercontent 只返回 LFS 指针，
    # 必须用 media.githubusercontent.com 才能拿到真正的二进制。
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
YUNET_DOWNLOAD_TIMEOUT: int = 30

# mediapipe 中文路径兼容 junction（ASCII 路径别名，指向 site-packages）
MP_JUNCTION: str = f"{os.environ.get('SystemDrive', 'C:')}\\dzhy_mp_ascii"
# YuNet 模型目录的 ASCII 别名（指向 model/ 目录，供 OpenCV DNN 读取）
MODEL_JUNCTION: str = f"{os.environ.get('SystemDrive', 'C:')}\\dzhy_model_ascii"

# lazy 单例缓存
_face_mesh: Any = None
_mp_checked: bool = False
_mtcnn: Any = None
_mtcnn_checked: bool = False
_yunet: Any = None
_yunet_checked: bool = False


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
        _ensure_mediapipe_ascii()
        import mediapipe as mp  # noqa: PLC0415 - 刻意 lazy 导入

        _face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=MAX_NUM_FACES,
            refine_landmarks=False,
            min_detection_confidence=0.5,
        )
        logger.info("mediapipe FaceMesh 初始化成功")
    except Exception as exc:
        _face_mesh = None
        logger.warning(f"mediapipe 不可用，将使用检测框兜底: {exc}", exc_info=True)
    return _face_mesh


def _site_packages_dir() -> Optional[str]:
    """定位 site-packages 目录（优先 venv 的 sys.path，退回 site.getsitepackages）。"""
    for p in sys.path:
        if p and (p.endswith("site-packages") or p.endswith("dist-packages")):
            return p
    try:
        sp = site.getsitepackages()
        return sp[0] if sp else None
    except Exception:
        return None


def _create_junction(link: str, target: str) -> None:
    """用 mklink /J 创建目录联接（junction 无需管理员权限）。"""
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", link, target],
        capture_output=True, text=True, timeout=30,
    )
    if not os.path.isdir(link):
        raise RuntimeError(f"mklink /J 失败: {result.stdout} {result.stderr}")


def _remove_junction(link: str) -> None:
    subprocess.run(["cmd", "/c", "rmdir", link], capture_output=True, timeout=30)


def _ensure_ascii_junction(target: str, link: str) -> bool:
    """确保目录 target 可经 ASCII 路径访问（供 C++ 层读取模型文件）。

    target 本身为 ASCII 时直接返回 True；否则在 link 处幂等创建指向 target 的
    junction 并返回是否可用。任何失败（C 盘不可写、mklink 失败）返回 False，
    绝不抛异常。测试/CI 可用 DZHY_DISABLE_JUNCTION=1 跳过。
    """
    if all(ord(c) < 128 for c in target):
        return True
    if os.environ.get("DZHY_DISABLE_JUNCTION") == "1":
        return False
    try:
        # 用 lexists 判断链接本身：损坏的 junction（目标被删/项目移动）ispath/islink 都返回
        # False，必须靠 lexists 才能发现并清理重建，否则 mklink 会因残留 reparse 点永久失败。
        if os.path.lexists(link):
            if os.path.isdir(link):
                try:
                    if os.path.realpath(link).lower() != target.lower():
                        _remove_junction(link)
                except Exception:
                    _remove_junction(link)
            else:
                _remove_junction(link)
        if not os.path.lexists(link):
            _create_junction(link, target)
        return os.path.isdir(link)
    except Exception as exc:
        logger.warning(f"ASCII junction 创建失败（{link} → {target}）: {exc}")
        return False


def _ensure_mediapipe_ascii() -> None:
    """mediapipe 中文路径兼容：C++ 层无法解析非 ASCII 模型路径。

    若 site-packages 路径含非 ASCII（如本项目的「丹智慧眼项目」），在系统盘建一个
    ASCII 路径的 junction 指向 site-packages，并把它插到 sys.path 最前，使后续
    `import mediapipe` 命中 ASCII 副本（mediapipe.__file__ 变为 ASCII → C++ 层
    能找到模型文件）。任何失败静默回退，绝不阻断。
    """
    if "mediapipe" in sys.modules:
        return  # 已导入，路径已固化，无法补救
    target = _site_packages_dir()
    if not target:
        return
    if _ensure_ascii_junction(target, MP_JUNCTION):
        if MP_JUNCTION not in sys.path:
            sys.path.insert(0, MP_JUNCTION)
        logger.info(f"mediapipe 中文路径兼容：已建 junction {MP_JUNCTION} → {target}")


def _yunet_model_ascii_path() -> Optional[Path]:
    """返回 OpenCV DNN 可读取的 ASCII 模型路径。

    OpenCV 的 ONNXImporter 与 mediapipe 相同，无法读取中文路径下的模型文件，
    因此经 ASCII junction 别名访问 model/ 目录。
    """
    if all(ord(c) < 128 for c in str(MODEL_DIR)):
        return YUNET_MODEL_PATH
    if _ensure_ascii_junction(str(MODEL_DIR), MODEL_JUNCTION):
        return Path(MODEL_JUNCTION) / YUNET_MODEL_PATH.name
    return None


def is_mediapipe_available() -> bool:
    """触发 lazy 导入并返回 mediapipe 是否可用（供健康检查使用）。

    返回:
        True 表示 geometric 路径可用。
    """
    return _get_face_mesh() is not None


def face_detector_status() -> dict:
    """返回各检测引擎可用性（供服务 /health 观察）。"""
    return {
        "mediapipe": is_mediapipe_available(),
        "yunet": _get_yunet() is not None,
        "mtcnn": _get_mtcnn() is not None,
    }


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
        logger.info("MTCNN 检测器初始化成功")
    except Exception as exc:
        _mtcnn = None
        logger.warning(f"MTCNN 不可用，将回退到 OpenCV Haar: {exc}", exc_info=True)
    return _mtcnn


def _download_yunet_model() -> None:
    """下载 YuNet ONNX 模型（~230KB）到 model/ 目录（经 ASCII junction 别名）。

    下载失败或无法获取 ASCII 路径时抛异常，由调用方降级处理。
    """
    path = _yunet_model_ascii_path()
    if path is None:
        raise RuntimeError("无法获取 YuNet 模型的 ASCII 路径")
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"正在下载 YuNet 人脸检测模型: {YUNET_MODEL_URL}")
    # 多 worker 并发时各用独立临时文件，避免互相截断；os.replace 保证最终文件原子落盘
    tmp = path.parent / f"{path.stem}.{os.getpid()}.tmp"
    with urllib.request.urlopen(YUNET_MODEL_URL, timeout=YUNET_DOWNLOAD_TIMEOUT) as resp, tmp.open("wb") as f:
        shutil.copyfileobj(resp, f)
    os.replace(tmp, path)
    logger.info(f"YuNet 模型已保存至 {path}")


def _get_yunet() -> Any:
    """lazy 初始化 OpenCV YuNet 人脸检测器；失败返回 None。

    返回:
        cv2.FaceDetectorYN 实例或 None。
    """
    global _yunet, _yunet_checked
    if _yunet is not None:
        return _yunet
    if _yunet_checked:
        return None
    _yunet_checked = True
    if os.environ.get("DZHY_DISABLE_YUNET") == "1":
        return None  # 测试/CI 关闭 YuNet，保持无网络依赖
    try:
        path = _yunet_model_ascii_path()
        # 真实模型约 227KB；过小说明是损坏文件或 GitHub LFS 指针，需重新下载
        if path is not None and (not path.exists() or path.stat().st_size < 50_000):
            _download_yunet_model()
        if path is not None and path.exists():
            _yunet = cv2.FaceDetectorYN.create(str(path), "", (320, 320))
            logger.info("YuNet 检测器初始化成功")
    except Exception as exc:
        _yunet = None
        logger.warning(f"YuNet 不可用，将使用 MTCNN: {exc}", exc_info=True)
    return _yunet


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


def _build_landmark_analysis(m: dict) -> list[dict]:
    """基于 5 关键点指标的兜底中文分析列表（3 项，与 468 点分析保持字段一致）。"""
    fa = m.get("face_ratio") or 0.0
    mr = m.get("mouth_ratio") or 0.0
    fe = m.get("face_to_eye_ratio") or 0.0

    def _face_len_desc(v: float) -> str:
        if v > LM_FACE_RATIO_LONG:
            return "脸偏长，适合横向扩张感、框高适中的镜框"
        if v < LM_FACE_RATIO_ROUND:
            return "脸偏短圆，适合有高度、能拉长脸型的镜框"
        return "脸长比例均衡，多数镜框都较协调"

    def _mouth_desc(v: float) -> str:
        if v >= LM_MOUTH_RATIO_FULL:
            return "嘴宽相对较宽，下颌饱满（方/圆脸倾向）"
        if v < LM_MOUTH_RATIO_ROUND:
            return "嘴宽相对较窄，下颌线条偏柔和（鹅蛋/瓜子脸倾向）"
        return "嘴宽适中"

    return [
        {"label": "脸长宽比", "value": f"{fa:.2f}", "desc": _face_len_desc(fa)},
        {"label": "嘴宽比", "value": f"{mr:.2f}", "desc": _mouth_desc(mr)},
        {"label": "脸宽/眼宽", "value": f"{fe:.1f}", "desc": "脸宽与眼距之比，越接近 5 越符合「三庭五眼」标准"},
    ]


def _explain_landmark_verdict(face_shape: str, m: dict) -> str:
    """生成 5 关键点兜底分类的中文判定依据。"""
    fa = m.get("face_ratio") or 0.0
    mr = m.get("mouth_ratio") or 0.0
    fe = m.get("face_to_eye_ratio") or 0.0
    if face_shape == "长方形":
        rule = f"脸长宽比 {fa:.2f} > {LM_FACE_RATIO_LONG}（长脸特征）"
    elif face_shape == "圆形":
        rule = (
            f"脸长宽比 {fa:.2f} < {LM_FACE_RATIO_ROUND} 且 "
            f"嘴宽比 {mr:.2f} ≥ {LM_MOUTH_RATIO_ROUND}（短圆脸、下颌饱满）"
        )
    elif face_shape == "方形":
        rule = (
            f"嘴宽比 {mr:.2f} ≥ {LM_MOUTH_RATIO_FULL} 且 "
            f"脸宽/眼宽 {fe:.1f} ≥ {LM_EYE_RATIO_WIDE}（方正下颌、脸偏宽）"
        )
    else:  # 鹅蛋脸
        rule = (
            f"脸长宽比 {fa:.2f} 适中，且嘴宽/脸宽比例不符合方脸或圆脸特征"
            f"（轮廓柔和、下巴微尖）"
        )
    return (
        f"判定为「{face_shape}」：{rule}。"
        f"（基于 5 关键点兜底分类，精度低于 468 点几何分析）"
    )


def _classify_by_landmarks(
    box: tuple[float, float, float, float],
    lm5: list[tuple[float, float]],
) -> tuple[str, dict, list[dict], str]:
    """用 5 关键点 + 检测框做脸型分类（fallback_landmark）。

    特征（与 IEEE 轻量脸型分类论文同构，未来可直接喂 sklearn DecisionTree）：
    - face_ratio        = 框高 / 框宽（脸长宽比）
    - mouth_ratio       = 嘴宽 / 脸宽（下颌饱满度代理）
    - face_to_eye_ratio = 脸宽 / 眼距（五眼宽窄）

    参数:
        box: (x, y, w, h) 人脸检测框。
        lm5: 5 关键点 [[x, y], ...]，顺序 [左眼, 右眼, 鼻, 左嘴角, 右嘴角]。

    返回:
        (face_shape, metrics, analysis, verdict)。
    """
    _, _, bw, bh = box

    def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    eye_w = _dist(lm5[0], lm5[1])
    mouth_w = _dist(lm5[3], lm5[4])
    face_ratio = bh / bw if bw > 1e-6 else 0.0
    mouth_ratio = mouth_w / bw if bw > 1e-6 else 0.0
    face_to_eye_ratio = bw / eye_w if eye_w > 1e-6 else 0.0

    metrics: dict = {
        "face_ratio": round(face_ratio, 3),
        "jaw_ratio": None,
        "forehead_ratio": None,
        "jaw_angle_deg": None,
        "upper_third_ratio": None,
        "lower_third_ratio": None,
        "face_to_eye_ratio": round(face_to_eye_ratio, 2),
        "mouth_ratio": round(mouth_ratio, 3),
        "nose_ratio": None,
    }

    if face_ratio > LM_FACE_RATIO_LONG:
        face_shape = "长方形"
    elif face_ratio < LM_FACE_RATIO_ROUND:
        face_shape = "圆形" if mouth_ratio >= LM_MOUTH_RATIO_ROUND else "鹅蛋脸"
    else:
        if mouth_ratio >= LM_MOUTH_RATIO_FULL and face_to_eye_ratio >= LM_EYE_RATIO_WIDE:
            face_shape = "方形"
        else:
            face_shape = "鹅蛋脸"
    return face_shape, metrics, _build_landmark_analysis(metrics), _explain_landmark_verdict(face_shape, metrics)


def _yunet_row_to_lm5(f: np.ndarray) -> list[tuple[float, float]]:
    """把 YuNet 的一行人脸结果转成内部关键点顺序。

    YuNet 输出为 N×15：[x, y, w, h, 右眼x, 右眼y, 左眼x, 左眼y, 鼻x, 鼻y,
    右嘴角x, 右嘴角y, 左嘴角x, 左嘴角y, score]。内部统一顺序为
    [左眼, 右眼, 鼻, 左嘴角, 右嘴角]。
    """
    return [
        (float(f[6]), float(f[7])),    # 左眼
        (float(f[4]), float(f[5])),    # 右眼
        (float(f[8]), float(f[9])),    # 鼻
        (float(f[12]), float(f[13])),  # 左嘴角
        (float(f[10]), float(f[11])),  # 右嘴角
    ]


def _detect_face(
    image_bgr: np.ndarray,
) -> Optional[tuple[tuple[float, float, float, float], Optional[list[tuple[float, float]]]]]:
    """检测人脸框与 5 个关键点（左眼/右眼/鼻/左嘴角/右嘴角）。

    检测顺序：YuNet（OpenCV DNN）→ MTCNN → OpenCV Haar。
    YuNet 与 MTCNN 均提供 5 关键点；Haar 仅返回检测框。

    参数:
        image_bgr: BGR 格式图像。

    返回:
        (box, lm5)：
        - box: (x, y, w, h) 像素坐标；
        - lm5: 5 个关键点 [[x, y], ...]，顺序为 [左眼, 右眼, 鼻, 左嘴角, 右嘴角]；
              无关键点时（Haar）为 None。
        所有检测器均不可用或未检出人脸时返回 None。
    """
    # YuNet 优先（更快、对侧脸/小脸更稳）
    yunet = _get_yunet()
    if yunet is not None:
        try:
            h, w = image_bgr.shape[:2]
            yunet.setInputSize((w, h))
            _, faces = yunet.detect(image_bgr)
            if faces is not None and len(faces) > 0:
                f = max(faces, key=lambda row: float(row[2]) * float(row[3]))  # 面积最大的人脸
                box = (float(f[0]), float(f[1]), float(f[2]), float(f[3]))
                return box, _yunet_row_to_lm5(f)
        except Exception as exc:
            logger.warning(f"YuNet 检测失败，回退 MTCNN: {exc}", exc_info=True)
    # MTCNN（返回 5 关键点，顺序恰好为内部顺序）
    mtcnn = _get_mtcnn()
    if mtcnn is not None:
        try:
            from PIL import Image  # noqa: PLC0415 - 刻意 lazy 导入

            rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            # landmarks=True 必须显式传入，否则只返回 (boxes, probs)，3 元解包会抛 ValueError
            boxes, _, landmarks = mtcnn.detect(Image.fromarray(rgb), landmarks=True)
            if boxes is not None and len(boxes) > 0:
                x1, y1, x2, y2 = (float(v) for v in boxes[0])
                if x2 > x1 and y2 > y1:
                    box = (x1, y1, x2 - x1, y2 - y1)
                    lm5: Optional[list[tuple[float, float]]] = None
                    if landmarks is not None and len(landmarks) > 0:
                        lm5 = [(float(px), float(py)) for px, py in landmarks[0]]
                    return box, lm5
        except Exception as exc:
            logger.warning(f"MTCNN 检测失败，回退到 OpenCV Haar: {exc}", exc_info=True)
    # OpenCV Haar（仅检测框，无关键点）
    try:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda b: int(b[2]) * int(b[3]))
            return (float(x), float(y), float(w), float(h)), None
    except Exception as exc:
        logger.warning(f"OpenCV Haar 检测失败: {exc}", exc_info=True)
    return None


def _detect_face_box(image_bgr: np.ndarray) -> Optional[tuple[float, float, float, float]]:
    """向后兼容薄包装：仅返回检测框 (x, y, w, h)。"""
    det = _detect_face(image_bgr)
    if det is None:
        return None
    box, _ = det
    return box


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
        - method: "geometric" / "fallback_landmark" / "fallback_box" / "unknown"。
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
    if len(image_bgr.shape) < 2:
        logger.warning("输入图像维度异常，无法识别人脸")
        return result

    h, w = image_bgr.shape[:2]
    if h < MIN_IMAGE_SIZE or w < MIN_IMAGE_SIZE:
        logger.warning(f"图片尺寸过小 {w}x{h}（小于 {MIN_IMAGE_SIZE}px），跳过人脸识别")
        result["reason"] = "图片尺寸过小，无法识别人脸"
        return result
    if h * w > MAX_IMAGE_AREA:
        scale = math.sqrt(MAX_IMAGE_AREA / float(h * w))
        new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
        logger.warning(f"图片面积过大 {w}x{h}，降采样至 {new_w}x{new_h} 后识别")
        image_bgr = cv2.resize(image_bgr, (new_w, new_h))
        h, w = new_h, new_w

    mesh = _get_face_mesh()
    box_detectors_ready = _get_mtcnn() is not None or cv2.data.haarcascades is not None
    if mesh is not None:
        result["method"] = "geometric"
        try:
            rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            res = mesh.process(rgb)
            if res.multi_face_landmarks:
                face_count = len(res.multi_face_landmarks)
                result["face_count"] = face_count
                if face_count > 1:
                    logger.warning(f"检测到 {face_count} 张人脸，取最宽人脸进行脸型识别")
                # 取颧骨宽最大的人脸作为主脸（MediaPipe 多脸顺序不保证按大小）
                primary = max(
                    res.multi_face_landmarks,
                    key=lambda fl: abs(fl.landmark[_IDX_CHEEK_R].x - fl.landmark[_IDX_CHEEK_L].x) * w,
                )
                lms = primary.landmark

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
                    if face_ratio < 0.5 or face_ratio > 3.0:
                        logger.warning(
                            f"异常脸长宽比 {face_ratio:.2f}（正常范围约 0.5~3.0），几何指标可能异常"
                        )
                    if mid_t > 1e-6:
                        upper_third_ratio: Optional[float] = round(upper_t / mid_t, 3)
                        lower_third_ratio: Optional[float] = round(lower_t / mid_t, 3)
                    else:
                        # mid_t 过小意味着中庭不可测，置 None 避免产出无意义的像素比值
                        upper_third_ratio = None
                        lower_third_ratio = None
                        logger.warning("中庭长度过小（mid_t≈0），上庭/下庭比例无法计算，置为 None")
                    metrics: dict = {
                        "face_ratio": round(face_ratio, 3),
                        "jaw_ratio": round(jaw_ratio, 3),
                        "forehead_ratio": round(forehead_ratio, 3),
                        "jaw_angle_deg": round(jaw_angle, 1),
                        "upper_third_ratio": upper_third_ratio,
                        "lower_third_ratio": lower_third_ratio,
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
                logger.warning("颧骨宽过小（cheek_w≈0），几何指标不可信，转用检测框兜底")
        except Exception as exc:
            # 关键点提取异常时继续走检测框兜底
            logger.warning(f"关键点几何提取失败，转用检测框兜底: {exc}", exc_info=True)
    elif box_detectors_ready:
        result["method"] = "fallback_box"
        logger.debug("mediapipe 不可用，启用检测框兜底路径")

    # 兜底：mediapipe 不可用或未检出人脸时，用检测框 + 5 关键点分类
    if result["method"] != "unknown":
        det = _detect_face(image_bgr)
        if det is not None:
            box, lm5 = det
            _, _, bw, bh = box
            if bw > 1e-6:
                result["face_count"] = 1
                if lm5 is not None:
                    face_shape, metrics, analysis, verdict = _classify_by_landmarks(box, lm5)
                    result["face_shape"] = face_shape
                    result["metrics"] = metrics
                    result["analysis"] = analysis
                    result["verdict"] = verdict
                    result["face_detected"] = True
                    result["method"] = "fallback_landmark"
                    logger.debug(f"5关键点兜底分类完成: {face_shape}")
                else:
                    result["face_shape"] = _classify_by_box(bh / bw)
                    result["face_detected"] = True
                    result["method"] = "fallback_box"
                    logger.debug(f"检测框兜底分类完成: {result['face_shape']}")
        elif result["method"] == "geometric":
            # geometric 路径实际没找到人脸，兜底也没找到 → 不再声称跑过几何分类
            result["method"] = "unknown"
    return result
