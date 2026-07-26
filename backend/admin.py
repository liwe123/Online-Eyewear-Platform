"""管理接口模块。

这里负责眼镜商品的增删改查以及 CSV 批量导入，所有接口都要求管理员权限。
"""
import csv
import io
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request

try:  # 支持包导入（gunicorn）与脚本直接运行两种方式
    from .auth import admin_required
    from .models import Glasses, db
except ImportError:  # pragma: no cover
    from auth import admin_required
    from models import Glasses, db

admin_bp: Blueprint = Blueprint("admin", __name__, url_prefix="/api/admin")

# CSV 导入要求的列头（与 data/glasses_data.csv 一致）
CSV_REQUIRED_COLUMNS = [
    "glasses_id", "frame_shape", "frame_size", "frame_material",
    "lens_degree_min", "lens_degree_max", "lens_refractive_index",
    "price", "image_url",
]

# 可写字段及其类型转换器（glasses_id 单独处理）
_FIELD_CASTERS: Dict[str, Any] = {
    "frame_shape": str,
    "frame_size": str,
    "frame_material": str,
    "lens_degree_min": float,
    "lens_degree_max": float,
    "lens_refractive_index": float,
    "price": float,
    "image_url": str,
}


def _apply_fields(glass: Glasses, data: Dict[str, Any]) -> Optional[str]:
    """把请求里的合法字段写入模型对象。

    返回值为错误信息；如果返回 `None`，说明所有字段都写入成功。
    """
    for field, caster in _FIELD_CASTERS.items():
        if field not in data:
            continue
        try:
            setattr(glass, field, caster(data[field]))
        except (ValueError, TypeError):
            return f"字段 {field} 取值非法"
    return None


@admin_bp.post("/glasses")
@admin_required
def create_glasses() -> Any:
    """创建眼镜（JSON 全字段），glasses_id 查重。"""
    data = request.get_json(silent=True) or {}
    glasses_id = str(data.get("glasses_id", "")).strip()
    if not glasses_id:
        return jsonify({"code": 400, "msg": "缺少 glasses_id"}), 400
    if Glasses.query.filter_by(glasses_id=glasses_id).first() is not None:
        return jsonify({"code": 400, "msg": f"glasses_id {glasses_id} 已存在"}), 400

    missing = [f for f in _FIELD_CASTERS if f not in data]
    if missing:
        return jsonify({"code": 400, "msg": f"缺少必填字段: {', '.join(missing)}"}), 400

    glass = Glasses(glasses_id=glasses_id)
    error = _apply_fields(glass, data)
    if error is not None:
        return jsonify({"code": 400, "msg": error}), 400
    db.session.add(glass)
    db.session.commit()
    return jsonify({"code": 200, "msg": "创建成功", "data": glass.to_dict()})


@admin_bp.put("/glasses/<glasses_id>")
@admin_required
def update_glasses(glasses_id: str) -> Any:
    """更新眼镜（JSON 部分字段）。"""
    glass = Glasses.query.filter_by(glasses_id=glasses_id).first()
    if glass is None:
        return jsonify({"code": 404, "msg": "眼镜不存在"}), 404
    data = request.get_json(silent=True) or {}
    error = _apply_fields(glass, data)
    if error is not None:
        return jsonify({"code": 400, "msg": error}), 400
    db.session.commit()
    return jsonify({"code": 200, "msg": "更新成功", "data": glass.to_dict()})


@admin_bp.delete("/glasses/<glasses_id>")
@admin_required
def delete_glasses(glasses_id: str) -> Any:
    """删除眼镜。"""
    glass = Glasses.query.filter_by(glasses_id=glasses_id).first()
    if glass is None:
        return jsonify({"code": 404, "msg": "眼镜不存在"}), 404
    db.session.delete(glass)
    db.session.commit()
    return jsonify({"code": 200, "msg": "删除成功"})


def _decode_csv(raw: bytes) -> Optional[str]:
    """按 utf-8-sig / gbk 顺序尝试解码 CSV 字节流。"""
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


@admin_bp.post("/glasses/import")
@admin_required
def import_glasses() -> Any:
    """批量导入眼镜 CSV。

    采用按 `glasses_id` upsert 的方式，既能批量导入，也能复用到管理员维护流程。
    """
    if "file" not in request.files:
        return jsonify({"code": 400, "msg": "缺少 csv 文件（字段名 file）"}), 400
    csv_file = request.files["file"]
    if not csv_file.filename:
        return jsonify({"code": 400, "msg": "未选择文件"}), 400

    text = _decode_csv(csv_file.read())
    if text is None:
        return jsonify({"code": 400, "msg": "CSV 编码不支持（仅支持 UTF-8/GBK）"}), 400

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or [h.strip() for h in reader.fieldnames] != CSV_REQUIRED_COLUMNS:
        return jsonify({"code": 400, "msg": f"CSV 列头须为: {','.join(CSV_REQUIRED_COLUMNS)}"}), 400

    imported = 0
    try:
        for row_number, row in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            if not row.get("glasses_id"):
                db.session.rollback()
                return jsonify({"code": 400, "msg": f"第{row_number}行缺少 glasses_id"}), 400
            glass = Glasses.query.filter_by(glasses_id=row["glasses_id"]).first()
            if glass is None:
                glass = Glasses(glasses_id=row["glasses_id"])
                db.session.add(glass)
            error = _apply_fields(glass, row)
            if error is not None:
                db.session.rollback()
                return jsonify({"code": 400, "msg": f"第{row_number}行：{error}"}), 400
            imported += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return jsonify({"code": 200, "data": {"imported": imported}})
