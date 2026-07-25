"""数据模型模块：集中定义 SQLAlchemy 实例与全部数据表。"""
from datetime import datetime
from typing import Optional

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db: SQLAlchemy = SQLAlchemy()


class User(db.Model):
    """用户表：存储用户的眼部参数（结构保持原样，仅新增可选的账号关联）。"""

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pupil_distance = db.Column(db.Float, nullable=False)  # 瞳距
    corneal_curvature = db.Column(db.Float, nullable=False)  # 角膜曲率
    myopia_degree = db.Column(db.Float, nullable=False)  # 近视度数
    create_time = db.Column(db.DateTime, default=datetime.now)  # 创建时间
    # 可选关联：提交时若携带有效 token，则记录对应账号
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=True)


class Glasses(db.Model):
    """眼镜表：存储眼镜商品信息（对应 glasses_data.csv）。"""

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

    def to_dict(self) -> dict:
        """序列化为接口返回字典。"""
        return {
            "glasses_id": self.glasses_id,
            "frame_shape": self.frame_shape,
            "frame_size": self.frame_size,
            "frame_material": self.frame_material,
            "lens_degree_min": self.lens_degree_min,
            "lens_degree_max": self.lens_degree_max,
            "lens_refractive_index": self.lens_refractive_index,
            "price": self.price,
            "image_url": self.image_url,
        }


class RecommendRecord(db.Model):
    """推荐记录表：存储用户的推荐历史。"""

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)  # 关联用户
    glasses_ids = db.Column(db.String(100), nullable=False)  # 推荐的眼镜ID（逗号分隔）
    face_shape = db.Column(db.String(20), nullable=False)  # 识别的脸型
    create_time = db.Column(db.DateTime, default=datetime.now)  # 创建时间


class Account(db.Model):
    """账号表：注册/登录账号，区分普通用户与管理员角色。"""

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(20), unique=True, nullable=False)  # 用户名（唯一）
    password_hash = db.Column(db.String(256), nullable=False)  # 密码哈希
    role = db.Column(db.String(10), nullable=False, default="user")  # 角色：user/admin
    create_time = db.Column(db.DateTime, default=datetime.now)  # 创建时间

    def set_password(self, password: str) -> None:
        """设置密码（以 werkzeug 哈希存储）。"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """校验明文密码是否匹配。"""
        return check_password_hash(self.password_hash, password)
