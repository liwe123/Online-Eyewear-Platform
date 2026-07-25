"""认证模块：基于 PyJWT 的注册/登录接口与 token 校验装饰器。"""
import functools
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Tuple

import jwt
from flask import Blueprint, g, jsonify, request

try:  # 支持包导入（gunicorn）与脚本直接运行两种方式
    from .models import Account, db
    from .settings import settings
except ImportError:  # pragma: no cover
    from models import Account, db
    from settings import settings

auth_bp: Blueprint = Blueprint("auth", __name__, url_prefix="/api/auth")

TOKEN_TTL_HOURS: int = 24  # token 有效期 24 小时
_JWT_ALGORITHM: str = "HS256"

# 用户名/密码长度约束
USERNAME_MIN, USERNAME_MAX = 3, 20
PASSWORD_MIN, PASSWORD_MAX = 6, 64


def generate_token(account: Account) -> str:
    """为指定账号生成 JWT，payload 含 account_id/username/role/exp。"""
    payload = {
        "account_id": account.id,
        "username": account.username,
        "role": account.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """解析 JWT，失败（过期/签名错误等）返回 None。"""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def _extract_token_payload() -> Tuple[Optional[dict], Optional[Any]]:
    """从 Authorization: Bearer <token> 中提取并校验 token。

    返回 (payload, error_response)：校验成功时 error_response 为 None。
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, (jsonify({"code": 401, "msg": "缺少或格式错误的认证令牌"}), 401)
    payload = decode_token(auth_header[len("Bearer "):].strip())
    if payload is None:
        return None, (jsonify({"code": 401, "msg": "令牌无效或已过期"}), 401)
    return payload, None


def token_required(func: Callable) -> Callable:
    """装饰器：要求携带有效 JWT，校验通过后账号信息挂在 flask.g.current_account。"""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        payload, error = _extract_token_payload()
        if error is not None:
            return error
        account = db.session.get(Account, payload["account_id"])
        if account is None:
            return jsonify({"code": 401, "msg": "账号不存在"}), 401
        g.current_account = account
        return func(*args, **kwargs)

    return wrapper


def admin_required(func: Callable) -> Callable:
    """装饰器：在 token_required 基础上要求 admin 角色，否则 403。"""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        payload, error = _extract_token_payload()
        if error is not None:
            return error
        account = db.session.get(Account, payload["account_id"])
        if account is None:
            return jsonify({"code": 401, "msg": "账号不存在"}), 401
        if account.role != "admin":
            return jsonify({"code": 403, "msg": "需要管理员权限"}), 403
        g.current_account = account
        return func(*args, **kwargs)

    return wrapper


def get_current_account_optional() -> Optional[Account]:
    """尝试解析请求中的 token（可选）：无 token 或无效时返回 None，不报错。"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    payload = decode_token(auth_header[len("Bearer "):].strip())
    if payload is None:
        return None
    return db.session.get(Account, payload["account_id"])


@auth_bp.post("/register")
def register() -> Any:
    """注册接口：校验用户名/密码长度，重名返回 400。"""
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if not (USERNAME_MIN <= len(username) <= USERNAME_MAX):
        return jsonify({"code": 400, "msg": f"用户名长度须为{USERNAME_MIN}-{USERNAME_MAX}个字符"}), 400
    if not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
        return jsonify({"code": 400, "msg": f"密码长度须为{PASSWORD_MIN}-{PASSWORD_MAX}个字符"}), 400
    if Account.query.filter_by(username=username).first() is not None:
        return jsonify({"code": 400, "msg": "用户名已存在"}), 400

    account = Account(username=username, role="user")
    account.set_password(password)
    db.session.add(account)
    db.session.commit()
    return jsonify({"code": 200, "msg": "注册成功", "data": {"user_id": account.id}})


@auth_bp.post("/login")
def login() -> Any:
    """登录接口：验证成功返回 token，失败统一返回 401。"""
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    account = Account.query.filter_by(username=username).first()
    if account is None or not account.check_password(password):
        return jsonify({"code": 401, "msg": "用户名或密码错误"}), 401

    token = generate_token(account)
    return jsonify({
        "code": 200,
        "data": {"token": token, "username": account.username, "role": account.role},
    })


def ensure_admin_account() -> None:
    """首次初始化时，若不存在 admin 账号则按 ADMIN_USERNAME/ADMIN_PASSWORD 创建。"""
    if Account.query.filter_by(role="admin").first() is None:
        admin = Account(username=settings.ADMIN_USERNAME, role="admin")
        admin.set_password(settings.ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()
