"""数据模型模块。

这里集中定义数据库实例和所有 ORM 模型，避免在业务代码里重复声明表结构。
"""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db: SQLAlchemy = SQLAlchemy()


class User(db.Model):
    """用户表。

    记录一次分析时输入的视力参数，并可选关联到登录账号。
    """

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pupil_distance = db.Column(db.Float, nullable=False)  # 瞳距
    corneal_curvature = db.Column(db.Float, nullable=False)  # 角膜曲率
    myopia_degree = db.Column(db.Float, nullable=False)  # 近视度数
    create_time = db.Column(db.DateTime, default=datetime.now)  # 创建时间
    # 可选关联：提交时若携带有效 token，则记录对应账号
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=True)


class Glasses(db.Model):
    """眼镜商品表。

    该表既用于推荐结果展示，也用于商城列表和详情页查询。
    """

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
    name = db.Column(db.String(120), nullable=True)  # 商品名称（真实数据可选）
    brand = db.Column(db.String(120), nullable=True)  # 品牌（真实数据可选）

    def to_dict(self) -> dict:
        """把 ORM 对象转换成前端可直接消费的字典。"""
        return {
            "glasses_id": self.glasses_id,
            "name": self.name,
            "brand": self.brand,
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
    """推荐记录表。

    保存用户提交参数对应的脸型和推荐结果，便于后续查询或统计分析。
    """

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)  # 关联用户
    glasses_ids = db.Column(db.Text, nullable=False)  # 推荐的眼镜ID（逗号分隔，可能超过100字符）
    face_shape = db.Column(db.String(20), nullable=False)  # 识别的脸型
    create_time = db.Column(db.DateTime, default=datetime.now)  # 创建时间


class Account(db.Model):
    """账号表。

    负责注册、登录以及管理员权限判断。
    """

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
