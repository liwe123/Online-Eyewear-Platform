import logging
from io import BytesIO
from fastapi import FastAPI, UploadFile, File
import uvicorn
import torch
import joblib
import numpy as np
import cv2
from PIL import Image
from facenet_pytorch import MTCNN
from pydantic import BaseModel
import pandas as pd
import os

from model_utils import FaceShapeCNN

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="丹智慧眼模型API")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

num_classes = 4
model = FaceShapeCNN(num_classes=num_classes)
model_path = "./model/face_shape_model.pth"
model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
model.to(device).eval()
logger.info(f"脸型识别模型加载完成，设备: {device}")

label_encoder = joblib.load("./model/label_encoder.pkl")
recommend_model = joblib.load("./model/recommend_model.pkl")
logger.info("推荐模型和标签编码器加载完成")

try:
    glasses_df = pd.read_csv("./data/glasses_data.csv", encoding="utf-8")
except UnicodeDecodeError:
    glasses_df = pd.read_csv("./data/glasses_data.csv", encoding="gbk")
except Exception:
    logger.warning("眼镜数据CSV加载失败，使用默认数据")
    glasses_df = pd.DataFrame({
        "glasses_id": ["def1", "def2", "def3"],
        "frame_shape": ["方形", "圆形", "鹅蛋形"],
        "frame_material": ["钛合金", "TR90", "纯钛"],
        "lens_refractive_index": [1.60, 1.74, 1.56],
        "price": [399, 499, 299],
        "image_url": ["https://img.example.com/def1.jpg", "https://img.example.com/def2.jpg", "https://img.example.com/def3.jpg"]
    })

mtcnn = MTCNN(image_size=160, margin=0, device=device)


class EyeData(BaseModel):
    pupil_distance: float
    corneal_curvature: float
    myopia_degree: float


@app.post("/predict_face_shape")
async def predict_face_shape(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        img = Image.open(BytesIO(contents)).convert("RGB")
        face = mtcnn(img)
        if face is None:
            face = torch.tensor(
                cv2.resize(np.array(img), (160, 160)),
                dtype=torch.float32
            ).permute(2, 0, 1) / 255.0
        else:
            face = face.to(dtype=torch.float32) / 255.0

        with torch.no_grad():
            face = face.unsqueeze(0).to(device)
            output = model(face)
            pred = torch.argmax(output, dim=1).cpu().numpy()[0]
            face_shape = label_encoder.inverse_transform([pred])[0]

        return {"code": 200, "face_shape": face_shape, "msg": "识别成功"}
    except Exception as e:
        logger.exception("脸型识别失败")
        return {"code": 500, "msg": f"识别失败: {str(e)}"}


@app.post("/get_recommendation")
async def get_recommendation(eye_data: EyeData, face_shape: str):
    try:
        X = np.array([[
            eye_data.pupil_distance,
            eye_data.corneal_curvature,
            eye_data.myopia_degree
        ]])
        pred_shape_idx = recommend_model.predict(X)[0]
        pred_shape = label_encoder.inverse_transform([pred_shape_idx])[0]

        match_glasses = glasses_df[
            glasses_df["frame_shape"].isin([pred_shape, face_shape])
        ].head(3)

        if len(match_glasses) == 0:
            match_glasses = glasses_df.head(3)

        recommendation = match_glasses[
            ["glasses_id", "frame_shape", "frame_material", "lens_refractive_index", "price", "image_url"]
        ].to_dict("records")
        return {"code": 200, "recommendation": recommendation, "msg": "推荐成功"}
    except Exception as e:
        logger.exception("推荐失败")
        return {"code": 500, "msg": f"推荐失败: {str(e)}"}


if __name__ == "__main__":
    port = int(os.environ.get("MODEL_PORT", "8000"))
    logger.info(f"模型API服务启动，端口: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
