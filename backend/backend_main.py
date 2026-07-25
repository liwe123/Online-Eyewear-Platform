"""丹智慧眼 Flask 后端主应用。

开发启动：
    python backend/backend_main.py
    或 python -m backend.backend_main

生产启动（gunicorn，项目根目录下执行）：
    gunicorn -w 4 -b 0.0.0.0:5000 "backend.backend_main:app"
"""
import sys
import time
from pathlib import Path
from typing import Any, Optional

import requests
from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from loguru import logger

# ---------- 双模式导入：兼容包导入（gunicorn）与脚本直接运行 ----------
try:
    from .admin import admin_bp
    from .auth import auth_bp, ensure_admin_account, get_current_account_optional
    from .models import Glasses, RecommendRecord, User, db
    from .settings import DATA_DIR, settings
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from admin import admin_bp
    from auth import auth_bp, ensure_admin_account, get_current_account_optional
    from models import Glasses, RecommendRecord, User, db
    from settings import DATA_DIR, settings

# ---------- 日志：loguru，logs/backend.log 按天轮转，stdout 同步 ----------
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
GLASSES_IMAGE_DIR = DATA_DIR / "glasses_images"
GLASSES_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(sys.stdout, level=settings.LOG_LEVEL, enqueue=True,
           format="{time:YYYY-MM-DD HH:mm:ss} [{level}] {message}")
logger.add(LOG_DIR / "backend.log", level=settings.LOG_LEVEL, rotation="00:00",
           retention="30 days", encoding="utf-8", enqueue=True,
           format="{time:YYYY-MM-DD HH:mm:ss} [{level}] {message}")

# ---------- 图片校验常量 ----------
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


def _allowed_image(filename: str) -> bool:
    """校验图片文件扩展名是否在白名单内。"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------- Flask 应用装配 ----------
app = Flask(__name__)
# 反向代理（Nginx）后取真实客户端 IP，否则限流全部命中代理地址
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
CORS(app, origins=settings.cors_origin_list)
app.config["SQLALCHEMY_DATABASE_URI"] = settings.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_SIZE  # 请求体上限 10MB

db.init_app(app)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)

# ---------- 限流：默认 120/min，敏感接口 10/min ----------
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["120/minute"],
    storage_uri="memory://",
)


# ---------- 请求日志与统一安全头 ----------
@app.before_request
def _start_timer() -> None:
    """记录请求开始时间，供 after_request 计算耗时。"""
    g._start_time = time.perf_counter()


@app.after_request
def _log_and_secure(response: Any) -> Any:
    """记录 method/path/status/耗时，并统一追加安全响应头。"""
    elapsed_ms = (time.perf_counter() - getattr(g, "_start_time", time.perf_counter())) * 1000
    logger.info(f"{request.method} {request.path} -> {response.status_code} ({elapsed_ms:.1f}ms)")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


# ---------- 统一 JSON 错误格式 ----------
@app.errorhandler(404)
def handle_404(_: Any) -> Any:
    """资源不存在。"""
    return jsonify({"code": 404, "msg": "资源不存在"}), 404


@app.errorhandler(405)
def handle_405(_: Any) -> Any:
    """请求方法不允许。"""
    return jsonify({"code": 405, "msg": "请求方法不允许"}), 405


@app.errorhandler(429)
def handle_429(_: Any) -> Any:
    """触发限流。"""
    return jsonify({"code": 429, "msg": "请求过于频繁，请稍后再试"}), 429


@app.errorhandler(500)
def handle_500(_: Any) -> Any:
    """服务器内部错误：记录完整堆栈，不向前端泄露。"""
    logger.exception(f"未处理异常: {request.method} {request.path}")
    return jsonify({"code": 500, "msg": "服务器内部错误，请稍后重试"}), 500


# ---------- 业务接口 ----------
@app.post("/api/user/submit")
def user_submit() -> Any:
    """用户提交接口：接收图片和眼部参数，调用模型API获取推荐结果。

    请求格式：form-data 包含 image（图片）、pupil_distance、corneal_curvature、myopia_degree。
    允许匿名提交；若携带有效 token，则将结果关联到对应账号。
    """
    try:
        # ---------- 1. 请求参数校验 ----------
        if "image" not in request.files:
            return jsonify({"code": 400, "msg": "缺少图片文件"}), 400
        image_file = request.files["image"]
        if not image_file.filename:
            return jsonify({"code": 400, "msg": "未选择图片"}), 400
        if not _allowed_image(image_file.filename):
            return jsonify({"code": 400, "msg": f"不支持的图片格式，仅支持: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

        try:
            pupil_distance = float(request.form.get("pupil_distance", 0))
            corneal_curvature = float(request.form.get("corneal_curvature", 0))
            myopia_degree = float(request.form.get("myopia_degree", 0))
        except (ValueError, TypeError):
            return jsonify({"code": 400, "msg": "眼部参数必须为有效数字"}), 400

        if not (30 <= pupil_distance <= 80):
            return jsonify({"code": 400, "msg": "瞳距数据异常，范围应为30-80mm"}), 400
        if not (30 <= corneal_curvature <= 50):
            return jsonify({"code": 400, "msg": "角膜曲率数据异常，范围应为30-50D"}), 400
        if not (-20 <= myopia_degree <= 10):
            return jsonify({"code": 400, "msg": "近视度数数据异常，范围应为-20~10"}), 400

        # ---------- 2. 读取图片并校验大小 ----------
        image_bytes = image_file.read()
        if len(image_bytes) > MAX_IMAGE_SIZE:
            return jsonify({"code": 400, "msg": f"图片大小超过限制（最大{MAX_IMAGE_SIZE // (1024 * 1024)}MB）"}), 400

        # ---------- 3. 调用模型API识别脸型 ----------
        face_shape_response = requests.post(
            f"{settings.MODEL_API_URL}/predict_face_shape",
            files={"file": (image_file.filename, image_bytes, image_file.content_type)},
            timeout=30,
        )
        if face_shape_response.status_code != 200:
            logger.error(f"脸型识别失败: {face_shape_response.text}")
            return jsonify({"code": 400, "msg": "脸型识别失败"}), 400
        face_shape_data = face_shape_response.json()
        if face_shape_data.get("code") != 200:
            return jsonify({"code": 400, "msg": face_shape_data.get("msg", "脸型识别失败")}), 400
        face_shape = face_shape_data["face_shape"]

        # ---------- 4. 调用模型API获取推荐 ----------
        recommend_response = requests.post(
            f"{settings.MODEL_API_URL}/get_recommendation",
            json={
                "pupil_distance": pupil_distance,
                "corneal_curvature": corneal_curvature,
                "myopia_degree": myopia_degree,
            },
            params={"face_shape": face_shape},
            timeout=30,
        )
        if recommend_response.status_code != 200:
            logger.error(f"推荐失败: {recommend_response.text}")
            return jsonify({"code": 400, "msg": "推荐失败"}), 400
        recommend_data = recommend_response.json()
        if recommend_data.get("code") != 200:
            return jsonify({"code": 400, "msg": recommend_data.get("msg", "推荐失败")}), 400
        recommendation = recommend_data["recommendation"]

        # ---------- 5. 所有远程调用成功后再写入数据库 ----------
        account: Optional[Any] = get_current_account_optional()
        user = User(
            pupil_distance=pupil_distance,
            corneal_curvature=corneal_curvature,
            myopia_degree=myopia_degree,
            account_id=account.id if account else None,
        )
        db.session.add(user)
        db.session.flush()
        user_id = user.id

        glasses_ids = ",".join([item["glasses_id"] for item in recommendation])
        record = RecommendRecord(user_id=user_id, glasses_ids=glasses_ids, face_shape=face_shape)
        db.session.add(record)
        db.session.commit()

        logger.info(f"用户{user_id}推荐完成，脸型={face_shape}，推荐{len(recommendation)}款眼镜")
        return jsonify({
            "code": 200,
            "msg": "提交成功",
            "data": {"user_id": user_id, "face_shape": face_shape, "recommendation": recommendation},
        })
    except requests.exceptions.Timeout:
        db.session.rollback()
        return jsonify({"code": 500, "msg": "模型服务响应超时，请稍后重试"}), 500
    except requests.exceptions.ConnectionError:
        db.session.rollback()
        return jsonify({"code": 500, "msg": "模型服务连接失败，请检查服务是否启动"}), 500
    except Exception:
        db.session.rollback()
        logger.exception("用户提交接口异常")
        return jsonify({"code": 500, "msg": "服务器内部错误，请稍后重试"}), 500


@app.get("/api/glasses/list")
def glasses_list() -> Any:
    """眼镜列表接口：分页 + 筛选。

    参数：page（默认1）、page_size（默认12，最大50）、frame_shape、material、
    min_price、max_price、keyword（模糊匹配 frame_shape/frame_material/glasses_id）。
    """
    try:
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 12)), 1), 50)
    except (ValueError, TypeError):
        return jsonify({"code": 400, "msg": "page/page_size 必须为整数"}), 400

    query = Glasses.query
    frame_shape = request.args.get("frame_shape")
    if frame_shape:
        query = query.filter(Glasses.frame_shape == frame_shape)
    material = request.args.get("material")
    if material:
        query = query.filter(Glasses.frame_material == material)
    try:
        if request.args.get("min_price") is not None:
            query = query.filter(Glasses.price >= float(request.args["min_price"]))
        if request.args.get("max_price") is not None:
            query = query.filter(Glasses.price <= float(request.args["max_price"]))
    except (ValueError, TypeError):
        return jsonify({"code": 400, "msg": "min_price/max_price 必须为数字"}), 400
    keyword = request.args.get("keyword")
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(db.or_(
            Glasses.frame_shape.like(like),
            Glasses.frame_material.like(like),
            Glasses.glasses_id.like(like),
        ))

    total = query.count()
    items = query.order_by(Glasses.id).offset((page - 1) * page_size).limit(page_size).all()
    return jsonify({
        "code": 200,
        "data": {
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    })


@app.get("/api/glasses/detail")
def glasses_detail() -> Any:
    """眼镜详情接口：根据 glasses_id 查询详情。"""
    glasses_id = request.args.get("glasses_id")
    glass = Glasses.query.filter_by(glasses_id=glasses_id).first()
    if not glass:
        return jsonify({"code": 404, "msg": "眼镜不存在"}), 404
    return jsonify({"code": 200, "data": glass.to_dict()})


@app.get("/static/glasses/<path:filename>")
def glasses_image(filename: str) -> Any:
    """眼镜图片静态服务：从 data/glasses_images/ 取文件（send_from_directory 自带路径穿越防护）。"""
    return send_from_directory(GLASSES_IMAGE_DIR, filename)


# ---------- 敏感接口限流（须在全部路由注册后应用） ----------
for _endpoint in ("auth.register", "auth.login", "user_submit"):
    app.view_functions[_endpoint] = limiter.limit("10/minute")(app.view_functions[_endpoint])


# ---------- 数据库初始化 ----------
def _load_glasses_from_df(glasses_df: Any) -> None:
    """将 DataFrame 中的眼镜数据导入数据库。"""
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
            image_url=row["image_url"],
        )
        db.session.add(glass)
    db.session.commit()


def init_db() -> None:
    """创建数据库表、加载眼镜 CSV 初始数据并确保 admin 账号存在。"""
    with app.app_context():
        db.create_all()
        if Glasses.query.count() == 0:
            import pandas as pd

            csv_path = DATA_DIR / "glasses_data.csv"
            if not csv_path.exists():
                logger.warning("glasses_data.csv 不存在，跳过数据导入")
            else:
                for encoding in ("utf-8", "gbk"):
                    try:
                        glasses_df = pd.read_csv(csv_path, encoding=encoding)
                        _load_glasses_from_df(glasses_df)
                        logger.info(f"数据库初始化成功（{encoding}编码），已加载眼镜数据")
                        break
                    except UnicodeDecodeError:
                        continue
                    except Exception as exc:
                        logger.error(f"加载眼镜数据失败({encoding})：{exc}")
                        break
                else:
                    logger.error("加载眼镜数据失败：不支持的编码格式")
        ensure_admin_account()
        logger.info("数据库初始化检查完成")


# 模块加载即初始化数据库（gunicorn 以包导入方式加载时 __name__ != "__main__"，
# 若只在 __main__ 分支初始化，容器部署下所有 DB 接口会因缺表而 500）
init_db()

# 生产环境使用默认密钥/口令时给出醒目警告
if settings.SECRET_KEY == "dev-secret-do-not-use-in-production-change-me":
    logger.warning("⚠️ 正在使用默认 SECRET_KEY，生产环境必须通过环境变量覆盖！")
if settings.ADMIN_PASSWORD == "admin123":
    logger.warning("⚠️ 正在使用默认 ADMIN_PASSWORD(admin123)，生产环境必须通过环境变量覆盖！")


# ---------- 启动服务 ----------
if __name__ == "__main__":
    logger.info(f"Flask 后端服务启动，端口: {settings.PORT}")
    app.run(host="0.0.0.0", port=settings.PORT, debug=False)
