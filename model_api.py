"""丹智慧眼模型服务（FastAPI）。

重构说明：
- 脸型识别由随机噪声训练的 CNN 更换为 MediaPipe FaceMesh 几何方案
  （见 face_geometry.py），不可用时降级为检测框启发式；
- 推荐由伪标签决策树更换为透明规则引擎（见 recommend_rules.py）；
- 不再加载 model/ 下的 .pth/.pkl 假模型文件。

API 契约（与 Flask 后端约定保持不变）：
- POST /predict_face_shape  multipart 字段 file → 脸型识别；
- POST /get_recommendation  JSON 眼部参数 + query 参数 face_shape → Top-N 推荐；
- GET  /health              服务健康状态。
"""
from __future__ import annotations

import math
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

import cv2
import numpy as np
import pandas as pd
import uvicorn
from fastapi import FastAPI, File, Query, Request, UploadFile
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from face_geometry import classify_face_shape, face_detector_status
from recommend_rules import RECOMMEND_FIELDS, recommend

# ---------------------------------------------------------------------------
# 配置（环境变量前缀 MODEL_）
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """服务配置。

    环境变量（前缀 MODEL_）：
    - MODEL_DIR       模型目录（历史遗留，几何方案已不读取其中文件）
    - MODEL_DATA_DIR  数据目录（glasses_data.csv 所在目录）
    - MODEL_PORT      服务端口
    - MODEL_LOG_LEVEL 日志级别
    """

    model_config = SettingsConfigDict(env_prefix="MODEL_", extra="ignore")

    dir: str = "./model"        # 环境变量 MODEL_DIR
    data_dir: str = "./data"    # 环境变量 MODEL_DATA_DIR
    port: int = 8000            # 环境变量 MODEL_PORT
    log_level: str = "INFO"     # 环境变量 MODEL_LOG_LEVEL


settings = Settings()

# ---------------------------------------------------------------------------
# 日志（loguru：stdout + 按天轮转文件）
# ---------------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
logger.remove()
logger.add(
    sys.stdout,
    level=settings.log_level,
    format="{time:YYYY-MM-DD HH:mm:ss} [{level}] {message}",
)
logger.add(
    "logs/model_api.log",
    level=settings.log_level,
    rotation="00:00",       # 按天轮转（每日零点切分）
    retention="30 days",
    encoding="utf-8",
    enqueue=True,
    format="{time:YYYY-MM-DD HH:mm:ss} [{level}] {message}",
)

DEFAULT_TOP_K: int = 3
MAX_IMAGE_SIZE: int = 10 * 1024 * 1024  # 10MB

# 眼镜 CSV 必需列（recommend_rules 打分与响应契约均依赖）
REQUIRED_CSV_COLUMNS: tuple[str, ...] = (
    "glasses_id",
    "name",
    "brand",
    "frame_shape",
    "frame_size",
    "frame_material",
    "lens_degree_min",
    "lens_degree_max",
    "lens_refractive_index",
    "price",
    "image_url",
)

# 资源字典：眼镜数据与分组索引
_resources: dict[str, Any] = {}


class EyeData(BaseModel):
    """用户眼部参数（近视度数为负值，如 -3.5 表示 350 度）。"""

    model_config = ConfigDict(allow_inf_nan=False)

    pupil_distance: float = Field(gt=30, lt=100, description="瞳距（毫米），生理范围约 30~100")
    corneal_curvature: float = Field(gt=30, lt=55, description="角膜曲率（毫米），生理范围约 30~55")
    myopia_degree: float = Field(
        description="近视度数：负数为屈光度（如 -3.5），正数为「度数」（如 350 表示 350 度）"
    )

    @field_validator("pupil_distance", "corneal_curvature", "myopia_degree")
    @classmethod
    def _reject_non_finite(cls, value: float) -> float:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ValueError("字段值不能为 NaN 或无穷大")
        return value

    @field_validator("myopia_degree")
    @classmethod
    def _validate_myopia_degree(cls, value: float) -> float:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ValueError("近视度数不能为 NaN 或无穷大")
        if not (-20000 < value < 2000):
            raise ValueError(
                "近视度数异常：允许范围 -20000~2000（正数为「度数」如 350，负数为屈光度如 -3.5），请检查单位"
            )
        return value


def _load_glasses_csv(csv_path: str) -> pd.DataFrame:
    """以 utf-8/gbk 双编码容错读取眼镜 CSV，并做基础清洗。

    参数:
        csv_path: CSV 文件路径。

    返回:
        清洗后的 DataFrame（shape 去空白、数值列转数值）。

    异常:
        ValueError: 所有编码均无法解析时抛出。
    """
    glasses_df: pd.DataFrame | None = None
    for encoding in ("utf-8", "gbk"):
        try:
            glasses_df = pd.read_csv(csv_path, encoding=encoding, skipinitialspace=True)
            logger.info(f"眼镜数据以 {encoding} 编码读取成功")
            break
        except UnicodeDecodeError:
            continue
    if glasses_df is None:
        # 最终兜底：替换非法字节，尽力加载（文件可能被并行任务写成混合编码）
        try:
            glasses_df = pd.read_csv(
                csv_path, encoding="utf-8", encoding_errors="replace", skipinitialspace=True
            )
            logger.warning("眼镜数据存在混合编码，非法字节已替换加载")
        except Exception as exc:
            raise ValueError(f"无法读取CSV文件: {csv_path}") from exc

    # 列校验：缺失必需列时给出明确错误，避免后续 KeyError 掩盖真实问题
    missing = [c for c in REQUIRED_CSV_COLUMNS if c not in glasses_df.columns]
    if missing:
        raise ValueError(f"眼镜CSV缺少必需列: {missing}，文件: {csv_path}")

    glasses_df["frame_shape"] = glasses_df["frame_shape"].astype(str).str.strip()
    for col in ("lens_degree_min", "lens_degree_max", "lens_refractive_index", "price"):
        glasses_df[col] = pd.to_numeric(glasses_df[col], errors="coerce")
    return glasses_df


def _load_resources() -> None:
    """加载服务资源（启动时调用一次）。

    这里做的是“只读预热”：提前把眼镜数据和分组索引放进内存，
    让推荐请求只做轻量过滤，避免每次请求都重新读 CSV。
    """
    global _resources

    # 旧版假模型文件废弃提示（不再加载 .pth/.pkl）
    for fname in ("face_shape_model.pth", "label_encoder.pkl", "recommend_model.pkl"):
        fpath = os.path.join(settings.dir, fname)
        if os.path.exists(fpath):
            logger.warning(f"检测到旧版模型文件 {fpath}，已废弃（几何方案不再加载），可安全删除")

    csv_path = os.path.join(settings.data_dir, "glasses_data.csv")
    glasses_df = _load_glasses_csv(csv_path)

    # 预建按 frame_shape 分组的索引，便于按形状快速筛选
    glasses_by_shape = {shape: group for shape, group in glasses_df.groupby("frame_shape")}
    logger.info(f"眼镜数据加载完成: {len(glasses_df)} 款，{len(glasses_by_shape)} 种形状")
    # 预热全部检测引擎（含 YuNet 首次下载），避免首个 /health 请求触发阻塞式联网下载
    det_status = face_detector_status()
    logger.info(
        "检测引擎: mediapipe={} yunet={} mtcnn={}".format(
            "可用" if det_status["mediapipe"] else "不可用",
            "可用" if det_status["yunet"] else "不可用",
            "可用" if det_status["mtcnn"] else "不可用",
        )
    )

    # 将可复用资源集中存放，后续请求直接读取内存对象即可。
    _resources = {
        "glasses_df": glasses_df,
        "glasses_by_shape": glasses_by_shape,
        "all_shapes": list(glasses_by_shape.keys()),
    }
    logger.info("模型服务初始化完成")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载资源。"""
    try:
        _load_resources()
    except Exception as exc:
        logger.error(f"模型服务初始化失败: {exc}")
        raise
    yield


app = FastAPI(title="丹智慧眼模型API", lifespan=lifespan)


# ---------- 请求耗时中间件 ----------
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """记录请求耗时，写入 X-Process-Time 响应头。

    这个头部主要用于调试和压测观察，不影响业务返回值。
    """
    start_time = time.time()
    response = await call_next(request)
    elapsed = time.time() - start_time
    response.headers["X-Process-Time"] = f"{elapsed:.3f}s"
    if elapsed > 2.0:
        logger.warning(f"慢请求: {request.method} {request.url.path} 耗时 {elapsed:.2f}s")
    return response


# ---------- 健康检查 ----------
@app.get("/health")
async def health_check() -> dict:
    """返回服务状态、检测引擎可用性与已加载眼镜数量。

    status 为 "ok" 表示资源正常加载；资源未加载时为 "degraded"（区别于
    正常加载但库存为 0 的情况），并附带 reason 说明。
    """
    detectors = face_detector_status()
    glasses_df = _resources.get("glasses_df")
    if glasses_df is None:
        return {
            "status": "degraded",
            "reason": "resources not loaded",
            "detectors": detectors,
            "mediapipe": detectors["mediapipe"],
            "glasses_count": 0,
        }
    return {
        "status": "ok",
        "detectors": detectors,
        "mediapipe": detectors["mediapipe"],
        "glasses_count": len(glasses_df),
    }


# ---------- 脸型识别 ----------
@app.post("/predict_face_shape")
async def predict_face_shape(file: UploadFile = File(...)) -> dict:
    """识别上传人脸照片的脸型。

    设计目标：
    - 正常情况下返回结构化的几何分析结果；
    - 未检测到人脸时使用“默认脸型”兜底，避免主流程中断；
    - 图片损坏或过大时返回明确业务错误，方便前端提示。
    """
    try:
        contents = await file.read()
        if len(contents) > MAX_IMAGE_SIZE:
            return {"code": 400, "msg": "图片大小超过10MB限制"}

        # OpenCV 解码失败通常意味着文件并非可识别图片。
        img = cv2.imdecode(np.frombuffer(contents, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return {"code": 400, "msg": "图片解码失败，请上传有效的图片文件"}

        result = classify_face_shape(img)
        if not result["face_detected"]:
            logger.info("未检测到人脸，返回默认脸型")
            return {
                "code": 200,
                "face_shape": "鹅蛋脸",
                "msg": "未检测到人脸，使用默认脸型",
                "method": "default",
                "metrics": {},
                "landmarks_count": 0,
                "landmarks": [],
                "analysis": [],
                "verdict": "",
            }

        logger.info(
            f"脸型识别: {result['face_shape']} (method={result['method']}, metrics={result['metrics']})"
        )
        return {
            "code": 200,
            "face_shape": result["face_shape"],
            "msg": "识别成功",
            "method": result["method"],
            "metrics": result["metrics"],
            "landmarks_count": result.get("landmarks_count", 0),
            "landmarks": result.get("landmarks", []),
            "analysis": result.get("analysis", []),
            "verdict": result.get("verdict", ""),
        }
    except KeyboardInterrupt:
        raise
    except SystemExit:
        raise
    except Exception:
        contents_len = len(contents) if "contents" in locals() else "?"
        logger.exception(
            f"脸型识别失败: endpoint=/predict_face_shape, file={file.filename}, size={contents_len}"
        )
        return {"code": 500, "msg": "识别失败，请稍后重试"}


# ---------- 眼镜推荐 ----------
@app.post("/get_recommendation")
async def get_recommendation(eye_data: EyeData, face_shape: str = Query(...)) -> dict:
    """按透明规则为用户推荐眼镜。

    这里优先做“可解释推荐”：返回结果列表的同时返回命中规则，
    方便前端展示，也方便后续调试推荐质量。
    """
    try:
        glasses_df = _resources.get("glasses_df")
        if glasses_df is None:
            return {"code": 500, "msg": "推荐资源未加载，请检查服务初始化"}

        items, rules = recommend(
            pupil_distance=eye_data.pupil_distance,
            corneal_curvature=eye_data.corneal_curvature,
            myopia_degree=eye_data.myopia_degree,
            face_shape=face_shape,
            glasses_df=glasses_df,
            top_n=DEFAULT_TOP_K,
        )
        recommendation = []
        for item in items:
            # 只返回前端需要的字段，减少响应体大小，也避免泄露无关内部信息。
            rec = {k: item.get(k) for k in RECOMMEND_FIELDS}
            rec["reason"] = item.get("reason")
            rec["score"] = item.get("score")
            recommendation.append(rec)
        logger.info(f"推荐完成: 脸型={face_shape}, 结果数={len(recommendation)}")
        return {"code": 200, "recommendation": recommendation, "msg": "推荐成功", "rules": rules}
    except KeyboardInterrupt:
        raise
    except SystemExit:
        raise
    except Exception:
        logger.exception(
            f"推荐失败: endpoint=/get_recommendation, face_shape={face_shape}, "
            f"pupil_distance={eye_data.pupil_distance}"
        )
        return {"code": 500, "msg": "推荐失败，请稍后重试"}


if __name__ == "__main__":
    logger.info(f"模型API服务启动，端口: {settings.port}")
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
