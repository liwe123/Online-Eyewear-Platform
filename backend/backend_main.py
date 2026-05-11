import os
import sys
import logging
from pathlib import Path
from flask import Flask, request, jsonify
import requests
from datetime import datetime

from config import db, MODEL_API_URL, BACKEND_PORT
from flask_cors import CORS

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["http://127.0.0.1:5500", "http://localhost:5500"])

# 配置数据库路径
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)  # 确保data目录存在
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATA_DIR / "backend.db"}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库
db.init_app(app)

# 数据模型定义
class User(db.Model):
    """用户表：存储用户的眼部参数"""
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pupil_distance = db.Column(db.Float, nullable=False)  # 瞳距
    corneal_curvature = db.Column(db.Float, nullable=False)  # 角膜曲率
    myopia_degree = db.Column(db.Float, nullable=False)  # 近视度数
    create_time = db.Column(db.DateTime, default=datetime.now)  # 创建时间

class Glasses(db.Model):
    """眼镜表：存储眼镜商品信息（对应glasses_data.csv）"""
    id = db.Column(db.Integer, primary_key=True)
    glasses_id = db.Column(db.String(20), unique=True, nullable=False)  # 眼镜唯一ID
    frame_shape = db.Column(db.String(20), nullable=False)  # 镜框形状
    frame_size = db.Column(db.String(20), nullable=False)  # 镜框尺寸
    frame_material = db.Column(db.String(20), nullable=False)  # 镜框材质
    lens_degree_min = db.Column(db.Float, nullable=False)  # 镜片最小度数
    lens_degree_max = db.Column(db.Float, nullable=False)  # 镜片最大度数
    lens_refractive_index = db.Column(db.Float, nullable=False)  # 镜片折射率
    price = db.Column(db.Float, nullable=False)  # 价格
    image_url = db.Column(db.String(200), nullable=False)  # 图片URL

class RecommendRecord(db.Model):
    """推荐记录表：存储用户的推荐历史"""
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 关联用户
    glasses_ids = db.Column(db.String(100), nullable=False)  # 推荐的眼镜ID（逗号分隔）
    face_shape = db.Column(db.String(20), nullable=False)  # 识别的脸型
    create_time = db.Column(db.DateTime, default=datetime.now)  # 创建时间

# 初始化数据库函数
def init_db():
    """创建数据库表并从CSV加载眼镜数据"""
    with app.app_context():
        db.create_all()
        if Glasses.query.count() == 0:
            import pandas as pd
            csv_path = DATA_DIR / "glasses_data.csv"
            if not csv_path.exists():
                logger.warning("glasses_data.csv 不存在，跳过数据导入")
                return
            try:
                glasses_df = pd.read_csv(csv_path, encoding="utf-8")
                for _, row in glasses_df.iterrows():
                    glass = Glasses(
                        glasses_id=row["glasses_id"],
                        frame_shape=row["frame_shape"],
                        frame_size=row["frame_size"],
                        frame_material=row["frame_material"],
                        lens_degree_min=float(row["lens_degree_min"]),
                        lens_degree_max=float(row["lens_degree_max"]),
                        lens_refractive_index=float(row["lens_refractive_index"]),
                        price=float(row["price"]),
                        image_url=row["image_url"]
                    )
                    db.session.add(glass)
                db.session.commit()
                logger.info("数据库初始化成功，已加载眼镜数据")
            except UnicodeDecodeError:
                try:
                    glasses_df = pd.read_csv(csv_path, encoding="gbk")
                    for _, row in glasses_df.iterrows():
                        glass = Glasses(
                            glasses_id=row["glasses_id"],
                            frame_shape=row["frame_shape"],
                            frame_size=row["frame_size"],
                            frame_material=row["frame_material"],
                            lens_degree_min=float(row["lens_degree_min"]),
                            lens_degree_max=float(row["lens_degree_max"]),
                            lens_refractive_index=float(row["lens_refractive_index"]),
                            price=float(row["price"]),
                            image_url=row["image_url"]
                        )
                        db.session.add(glass)
                    db.session.commit()
                    logger.info("数据库初始化成功（GBK编码），已加载眼镜数据")
                except Exception as e:
                    logger.error(f"加载眼镜数据失败(GBK)：{e}")
            except Exception as e:
                logger.error(f"加载眼镜数据失败：{e}")

# 接口定义
@app.post("/api/user/submit")
def user_submit():
    """
    用户提交接口：接收图片和眼部参数，调用模型API获取推荐结果
    请求格式：form-data包含image（图片）、pupil_distance、corneal_curvature、myopia_degree
    """
    try:
        if "image" not in request.files:
            return jsonify({"code": 400, "msg": "缺少图片文件"})
        image_file = request.files["image"]
        if image_file.filename == "":
            return jsonify({"code": 400, "msg": "未选择图片"})

        pupil_distance = float(request.form.get("pupil_distance", 0))
        corneal_curvature = float(request.form.get("corneal_curvature", 0))
        myopia_degree = float(request.form.get("myopia_degree", 0))

        if not (30 <= pupil_distance <= 80):
            return jsonify({"code": 400, "msg": "瞳距数据异常，范围应为30-80mm"})
        if not (30 <= corneal_curvature <= 50):
            return jsonify({"code": 400, "msg": "角膜曲率数据异常，范围应为30-50D"})
        if not (-20 <= myopia_degree <= 10):
            return jsonify({"code": 400, "msg": "近视度数数据异常，范围应为-20~10"})

        user = User(
            pupil_distance=pupil_distance,
            corneal_curvature=corneal_curvature,
            myopia_degree=myopia_degree
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        image_bytes = image_file.read()
        image_file.seek(0)

        face_shape_response = requests.post(
            f"{MODEL_API_URL}/predict_face_shape",
            files={"file": (image_file.filename, image_bytes, image_file.content_type)},
            timeout=30
        )
        if face_shape_response.status_code != 200:
            logger.error(f"脸型识别失败: {face_shape_response.text}")
            return jsonify({"code": 400, "msg": "脸型识别失败"})
        face_shape_data = face_shape_response.json()
        if face_shape_data.get("code") != 200:
            return jsonify({"code": 400, "msg": face_shape_data.get("msg", "脸型识别失败")})
        face_shape = face_shape_data["face_shape"]

        recommend_response = requests.post(
            f"{MODEL_API_URL}/get_recommendation",
            json={
                "pupil_distance": pupil_distance,
                "corneal_curvature": corneal_curvature,
                "myopia_degree": myopia_degree
            },
            params={"face_shape": face_shape},
            timeout=30
        )
        if recommend_response.status_code != 200:
            logger.error(f"推荐失败: {recommend_response.text}")
            return jsonify({"code": 400, "msg": "推荐失败"})
        recommend_data = recommend_response.json()
        if recommend_data.get("code") != 200:
            return jsonify({"code": 400, "msg": recommend_data.get("msg", "推荐失败")})
        recommendation = recommend_data["recommendation"]

        glasses_ids = ",".join([item["glasses_id"] for item in recommendation])
        record = RecommendRecord(
            user_id=user_id,
            glasses_ids=glasses_ids,
            face_shape=face_shape
        )
        db.session.add(record)
        db.session.commit()

        return jsonify({
            "code": 200,
            "msg": "提交成功",
            "data": {
                "user_id": user_id,
                "face_shape": face_shape,
                "recommendation": recommendation
            }
        })
    except requests.exceptions.Timeout:
        db.session.rollback()
        return jsonify({"code": 500, "msg": "模型服务响应超时，请稍后重试"})
    except requests.exceptions.ConnectionError:
        db.session.rollback()
        return jsonify({"code": 500, "msg": "模型服务连接失败，请检查服务是否启动"})
    except Exception as e:
        db.session.rollback()
        logger.exception("用户提交接口异常")
        return jsonify({"code": 500, "msg": f"服务器错误：{str(e)}"})

@app.get("/api/glasses/detail")
def glasses_detail():
    """
    眼镜详情接口：根据眼镜ID查询详情
    请求参数：glasses_id（眼镜唯一ID）
    """
    glasses_id = request.args.get("glasses_id")
    glass = Glasses.query.filter_by(glasses_id=glasses_id).first()
    if not glass:
        return jsonify({"code": 404, "msg": "眼镜不存在"})
    return jsonify({
        "code": 200,
        "data": {
            "glasses_id": glass.glasses_id,
            "frame_shape": glass.frame_shape,
            "frame_size": glass.frame_size,
            "frame_material": glass.frame_material,
            "lens_degree_min": glass.lens_degree_min,
            "lens_degree_max": glass.lens_degree_max,
            "lens_refractive_index": glass.lens_refractive_index,
            "price": glass.price,
            "image_url": glass.image_url
        }
    })

# 启动服务
if __name__ == "__main__":
    init_db()
    logger.info(f"Flask 后端服务启动，端口: {BACKEND_PORT}")
    app.run(host="0.0.0.0", port=BACKEND_PORT, debug=True)