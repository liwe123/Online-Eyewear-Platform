import logging
import time
import os
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import FastAPI, UploadFile, File, Request
import uvicorn
import torch
import joblib
import numpy as np
import cv2
from PIL import Image
from facenet_pytorch import MTCNN
from pydantic import BaseModel
import pandas as pd

from model_utils import FaceShapeCNN

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "./model")
DATA_DIR = os.environ.get("DATA_DIR", "./data")
DEFAULT_TOP_K = 3

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 使用字典存放模型资源，便于统一管理和重置
_resources: dict = {}


class EyeData(BaseModel):
    pupil_distance: float
    corneal_curvature: float
    myopia_degree: float


def _load_resources():
    """加载所有模型和数据资源（启动时调用）"""
    global _resources

    # 脸型识别模型
    num_classes = 4
    model = FaceShapeCNN(num_classes=num_classes)
    model_path = os.path.join(MODEL_DIR, "face_shape_model.pth")
    model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
    model.to(device).eval()
    logger.info(f"脸型识别模型加载完成，设备: {device}")

    # 标签编码器和推荐模型
    label_encoder = joblib.load(os.path.join(MODEL_DIR, "label_encoder.pkl"))
    recommend_model = joblib.load(os.path.join(MODEL_DIR, "recommend_model.pkl"))
    logger.info("推荐模型和标签编码器加载完成")

    # 眼镜数据
    csv_path = os.path.join(DATA_DIR, "glasses_data.csv")
    for encoding in ("utf-8", "gbk"):
        try:
            glasses_df = pd.read_csv(csv_path, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    if glasses_df is None:
        raise ValueError(f"无法读取CSV文件: {csv_path}")

    # 预建按 frame_shape 分组的索引，加速查找
    glasses_by_shape = {shape: df for shape, df in glasses_df.groupby("frame_shape")}
    all_shapes_list = list(glasses_by_shape.keys())
    logger.info(f"眼镜数据加载完成: {len(glasses_df)} 款，{len(all_shapes_list)} 种形状")

    # MTCNN 人脸检测器
    mtcnn = MTCNN(image_size=160, margin=0, device=device)

    _resources = {
        "model": model,
        "label_encoder": label_encoder,
        "recommend_model": recommend_model,
        "glasses_df": glasses_df,
        "glasses_by_shape": glasses_by_shape,
        "all_shapes": all_shapes_list,
        "mtcnn": mtcnn,
    }
    logger.info("模型服务初始化完成")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _load_resources()
    except Exception as e:
        logger.error(f"模型服务初始化失败: {e}")
        raise
    yield


app = FastAPI(title="丹智慧眼模型API", lifespan=lifespan)


# ---------- 请求耗时中间件 ----------
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    elapsed = time.time() - start_time
    # 写入响应头，便于调试
    response.headers["X-Process-Time"] = f"{elapsed:.3f}s"
    if elapsed > 2.0:
        logger.warning(f"慢请求: {request.method} {request.url.path} 耗时 {elapsed:.2f}s")
    return response


# ---------- 健康检查 ----------
@app.get("/health")
async def health_check():
    return {"status": "ok", "device": str(device), "glasses_count": len(_resources.get("glasses_df", []))}


# ---------- 脸型识别 ----------
@app.post("/predict_face_shape")
async def predict_face_shape(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        if len(contents) > 10 * 1024 * 1024:
            return {"code": 400, "msg": "图片大小超过10MB限制"}

        img = Image.open(BytesIO(contents)).convert("RGB")
        mtcnn = _resources["mtcnn"]
        model = _resources["model"]
        label_encoder = _resources["label_encoder"]

        face = mtcnn(img)
        if face is None:
            # 降级：直接缩放原图
            img_resized = cv2.resize(np.array(img), (160, 160))
            face = torch.tensor(img_resized, dtype=torch.float32).permute(2, 0, 1)
            face = (face / 127.5) - 1.0
        else:
            face = face.to(dtype=torch.float32)

        with torch.no_grad():
            face = face.unsqueeze(0).to(device)
            output = model(face)
            pred = torch.argmax(output, dim=1).cpu().numpy()[0]
            face_shape = label_encoder.inverse_transform([pred])[0]

        logger.info(f"脸型识别: {face_shape}")
        return {"code": 200, "face_shape": face_shape, "msg": "识别成功"}
    except Exception:
        logger.exception("脸型识别失败")
        return {"code": 500, "msg": "识别失败，请稍后重试"}


# ---------- 眼镜推荐 ----------
@app.post("/get_recommendation")
async def get_recommendation(eye_data: EyeData, face_shape: str):
    try:
        recommend_model = _resources["recommend_model"]
        label_encoder = _resources["label_encoder"]
        glasses_by_shape = _resources["glasses_by_shape"]
        glasses_df = _resources["glasses_df"]
        all_shapes = _resources["all_shapes"]

        # 模型预测推荐形状
        X = np.array([[
            eye_data.pupil_distance,
            eye_data.corneal_curvature,
            eye_data.myopia_degree
        ]])
        pred_shape_idx = recommend_model.predict(X)[0]
        pred_shape = label_encoder.inverse_transform([pred_shape_idx])[0]

        # 优先匹配模型预测形状或 AI 识别形状
        candidate_shapes = [s for s in (pred_shape, face_shape) if s in glasses_by_shape]
        if not candidate_shapes:
            candidate_shapes = all_shapes

        # 取前 DEFAULT_TOP_K 款
        match_glasses = pd.concat(
            [glasses_by_shape[s] for s in candidate_shapes], ignore_index=True
        ).drop_duplicates(subset="glasses_id").head(DEFAULT_TOP_K)

        recommendation = match_glasses[
            ["glasses_id", "frame_shape", "frame_material", "lens_refractive_index", "price", "image_url"]
        ].to_dict("records")

        logger.info(f"推荐完成: 脸型={face_shape}, 推荐形状={pred_shape}, 结果数={len(recommendation)}")
        return {"code": 200, "recommendation": recommendation, "msg": "推荐成功"}
    except Exception:
        logger.exception("推荐失败")
        return {"code": 500, "msg": "推荐失败，请稍后重试"}


if __name__ == "__main__":
    port = int(os.environ.get("MODEL_PORT", "8000"))
    logger.info(f"模型API服务启动，端口: {port}，设备: {device}")
    uvicorn.run(app, host="0.0.0.0", port=port)
