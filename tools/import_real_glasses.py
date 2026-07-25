# -*- coding: utf-8 -*-
"""丹智慧眼 - 真实商品数据导入器

把🍐总提供的真实眼镜商品文件（CSV / Excel）转换成项目标准格式并写入
data/glasses_data.csv（推荐源），同时（--resync）重刷 SQLite 商城库，
保证「推荐源」与「商城源」一致，解决历史双源不同步问题。

列映射对中文/英文表头及常见别名都做了容错，frame_shape 会归一到
项目规定的 6 种标准框型；材质/度数/折射率/价格也会做归一与校验。

用法:
    python tools/import_real_glasses.py <源文件.csv|.xlsx> [--resync] [--no-svg]

    --resync : 写完 CSV 后，清空 SQLite 眼镜表，使后端下次启动从新 CSV 重新种子
    --no-svg : 不为缺失图片的条目生成 SVG 占位图
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("import_real_glasses")

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
IMG_DIR = DATA_DIR / "glasses_images"
CSV_PATH = DATA_DIR / "glasses_data.csv"
DB_PATH = DATA_DIR / "backend.db"

# 标准字段顺序（CSV 契约）
FIELDS = [
    "glasses_id", "name", "brand", "frame_shape", "frame_size",
    "frame_material", "lens_degree_min", "lens_degree_max",
    "lens_refractive_index", "price", "image_url",
]

# 源表头 -> 标准字段（key 为「去空白+转小写+去标点」后的归一串）
_COLUMN_ALIASES = {
    "glassesid": "glasses_id", "id": "glasses_id", "商品id": "glasses_id",
    "眼镜id": "glasses_id", "货号": "glasses_id", "sku": "glasses_id", "编号": "glasses_id",
    "name": "name", "名称": "name", "商品名称": "name", "品名": "name",
    "型号": "name", "款式": "name", "商品": "name", "标题": "name",
    "brand": "brand", "品牌": "brand",
    "frameshape": "frame_shape", "镜框形状": "frame_shape", "框型": "frame_shape",
    "形状": "frame_shape", "脸型": "frame_shape", "frame": "frame_shape",
    "framesize": "frame_size", "尺寸": "frame_size", "镜框尺寸": "frame_size",
    "规格": "frame_size", "框尺寸": "frame_size",
    "framematerial": "frame_material", "材质": "frame_material",
    "镜框材质": "frame_material", "材料": "frame_material", "frame": "frame_material",
    "lensdegreemin": "lens_degree_min", "最小度数": "lens_degree_min",
    "度数下限": "lens_degree_min", "近视下限": "lens_degree_min", "度min": "lens_degree_min",
    "lensdegreemax": "lens_degree_max", "最大度数": "lens_degree_max",
    "度数上限": "lens_degree_max", "近视上限": "lens_degree_max", "度max": "lens_degree_max",
    "lensrefractiveindex": "lens_refractive_index", "折射率": "lens_refractive_index",
    "镜片折射率": "lens_refractive_index", "折射率指数": "lens_refractive_index",
    "price": "price", "价格": "price", "售价": "price", "单价": "price", "价钱": "price",
    "imageurl": "image_url", "图片": "image_url", "图片地址": "image_url",
    "图片链接": "image_url", "图": "image_url", "图片url": "image_url",
}

# 标准框型 + 别名归一
FRAME_SHAPE_CANON = ["长方形", "猫眼形", "圆形", "鹅蛋形", "方形", "多边形"]
_FRAME_SHAPE_SYN = {
    "长方": "长方形", "矩形": "长方形", "rectangle": "长方形", "rect": "长方形",
    "猫眼": "猫眼形", "catseye": "猫眼形", "cat": "猫眼形",
    "圆": "圆形", "round": "圆形",
    "鹅蛋": "鹅蛋形", "椭圆": "鹅蛋形", "oval": "鹅蛋形",
    "方": "方形", "square": "方形", "方圆": "方形",
    "多边形": "多边形", "六边": "多边形", "六边形": "多边形",
    "hexagon": "多边形", "poly": "多边形",
    "飞行员": "鹅蛋形", "aviator": "鹅蛋形",
    "蝴蝶": "猫眼形", "butterfly": "猫眼形",
}

# 标准材质 + 别名归一
MATERIAL_CANON = ["纯钛", "钛合金", "板材", "复合板材", "TR90", "金属", "合金"]
_MATERIAL_SYN = {
    "钛": "纯钛", "纯钛": "纯钛", "titanium": "纯钛",
    "钛合金": "钛合金", "ti-alloy": "钛合金",
    "板材": "板材", "板木": "板材", "acetate": "板材", "ac": "板材",
    "复合板材": "复合板材", "复合": "复合板材",
    "tr90": "TR90", "tr-90": "TR90",
    "金属": "金属", "metal": "金属", "金": "金属",
    "合金": "合金", "alloy": "合金",
}

REFRACTIVE_OPTIONS = (1.56, 1.60, 1.67, 1.71, 1.74)
# 两位数简写 -> 标准折射率
_REFRACTIVE_TWO_DIGIT = {56: 1.56, 60: 1.60, 67: 1.67, 71: 1.71, 74: 1.74}


def _norm_key(s: str) -> str:
    """表头归一：去空白、转小写、去中英文标点。"""
    s = (s or "").strip().lower()
    s = re.sub(r"[\s\-_/（）()：:，,.。、]+", "", s)
    return s


def build_column_map(headers: list[str]) -> dict[int, str]:
    """返回 {源列索引: 标准字段}。"""
    mapping: dict[int, str] = {}
    for i, h in enumerate(headers):
        key = _norm_key(h)
        if key in _COLUMN_ALIASES:
            mapping[i] = _COLUMN_ALIASES[key]
        elif key in FIELDS:
            mapping[i] = key
    return mapping


def normalize_frame_shape(s: str) -> str | None:
    if not s:
        return None
    t = (s or "").strip()
    if t in FRAME_SHAPE_CANON:
        return t
    key = _norm_key(t)
    if key in _FRAME_SHAPE_SYN:
        return _FRAME_SHAPE_SYN[key]
    # 子串兜底
    for syn, canon in _FRAME_SHAPE_SYN.items():
        if syn in key or syn in t:
            return canon
    for canon in FRAME_SHAPE_CANON:
        if canon in t:
            return canon
    logger.warning("无法识别的框型「%s」，将标记为「未知」并跳过该行", t)
    return None


def normalize_material(s: str) -> str:
    if not s:
        return "TR90"
    t = (s or "").strip()
    if t in MATERIAL_CANON:
        return t
    key = _norm_key(t)
    if key in _MATERIAL_SYN:
        return _MATERIAL_SYN[key]
    for syn, canon in _MATERIAL_SYN.items():
        if syn in key or syn in t:
            return canon
    logger.warning("未识别材质「%s」，按 TR90 处理", t)
    return "TR90"


def normalize_refractive_index(x: object) -> float:
    try:
        v = float(str(x).strip())
    except (ValueError, TypeError):
        logger.warning("折射率「%s」非法，默认 1.60", x)
        return 1.60
    if v in REFRACTIVE_OPTIONS:
        return v
    if int(round(v)) in _REFRACTIVE_TWO_DIGIT:
        return _REFRACTIVE_TWO_DIGIT[int(round(v))]
    # 取最接近的标准值
    return min(REFRACTIVE_OPTIONS, key=lambda c: abs(c - v))


def parse_floats(s: object) -> list[float]:
    """从文本中抽取所有浮点数（支持「-6.00~-1.00」「−3.00 至 0」等写法）。"""
    if s is None:
        return []
    text = str(s).replace("−", "-").replace("～", "~").replace("—", "-")
    return [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", text)]


def parse_degree(s: object) -> tuple[float, float]:
    nums = parse_floats(s)
    if not nums:
        return -6.0, -0.25
    if len(nums) == 1:
        v = nums[0]
        logger.warning("度数仅提供单一值 %s，按「%s~%s」处理（请确认范围）", v, v, v)
        return v, v
    return min(nums), max(nums)


def parse_price(s: object) -> float:
    nums = parse_floats(str(s).replace("¥", "").replace(",", ""))
    if not nums:
        return 0.0
    return round(float(nums[0]), 2)


def read_source(path: Path) -> tuple[list[str], list[dict]]:
    """读取 CSV / Excel，返回 (表头, 行字典列表)。"""
    suffix = path.suffix.lower()
    if suffix in (".csv", ".txt"):
        for enc in ("utf-8-sig", "utf-8", "gbk"):
            try:
                with path.open(encoding=enc, newline="") as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                if not rows:
                    continue
                headers = rows[0]
                data = [dict(zip(headers, r)) for r in rows[1:] if any(c.strip() for c in r)]
                return headers, data
            except UnicodeDecodeError:
                continue
        raise ValueError(f"无法解码文件: {path}")
    if suffix in (".xlsx", ".xls"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise RuntimeError("读取 Excel 需要 openpyxl，请先 pip install openpyxl")
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.values)
        if not rows:
            raise ValueError("Excel 为空")
        headers = [str(h) if h is not None else "" for h in rows[0]]
        data = []
        for r in rows[1:]:
            if r is None or all(c is None or str(c).strip() == "" for c in r):
                continue
            data.append({headers[i]: (r[i] if i < len(r) else None) for i in range(len(headers))})
        return headers, data
    raise ValueError(f"不支持的文件类型: {suffix}")


def transform(headers: list[str], raw_rows: list[dict]) -> list[dict]:
    col_map = build_column_map(headers)
    if "frame_shape" not in col_map.values():
        raise ValueError("源文件缺少「镜框形状/frame_shape」列，无法导入")
    out: list[dict] = []
    auto_id = 1
    for idx, row in enumerate(raw_rows, 1):
        rec = {k: "" for k in FIELDS}
        for src_i, field in col_map.items():
            rec[field] = row.get(headers[src_i], "")
        # 框型归一
        fs = normalize_frame_shape(rec.get("frame_shape", ""))
        if fs is None:
            logger.warning("第 %d 行框型无法识别，跳过", idx)
            continue
        rec["frame_shape"] = fs
        rec["frame_material"] = normalize_material(rec.get("frame_material", ""))
        dmin, dmax = parse_degree(rec.get("lens_degree_min", ""))
        # 若只有单一列，尝试用 max 列补范围
        if dmin == dmax and rec.get("lens_degree_max"):
            dmin2, dmax2 = parse_degree(rec.get("lens_degree_max", ""))
            dmin, dmax = min(dmin, dmin2, dmax, dmax2), max(dmin, dmin2, dmax, dmax2)
        rec["lens_degree_min"] = f"{dmin:.2f}"
        rec["lens_degree_max"] = f"{dmax:.2f}"
        rec["lens_refractive_index"] = normalize_refractive_index(rec.get("lens_refractive_index", ""))
        rec["price"] = parse_price(rec.get("price", ""))
        # 镜框尺寸规整
        rec["frame_size"] = _normalize_size(rec.get("frame_size", ""))
        # 图片：缺省则走 SVG 占位
        img = (rec.get("image_url", "") or "").strip()
        if not img:
            img = f"/static/glasses/{rec.get('glasses_id') or f'G{auto_id:03d}'}.svg"
        rec["image_url"] = img
        # 自动编号
        gid = (rec.get("glasses_id", "") or "").strip()
        if not gid:
            gid = f"G{auto_id:03d}"
            auto_id += 1
        rec["glasses_id"] = gid
        out.append(rec)
    # 去重 glasses_id
    seen = set()
    deduped = []
    for r in out:
        if r["glasses_id"] in seen:
            logger.warning("重复 glasses_id %s，跳过", r["glasses_id"])
            continue
        seen.add(r["glasses_id"])
        deduped.append(r)
    return deduped


def _normalize_size(s: str) -> str:
    # 尺寸用纯数字提取（避免把分隔符 '-' 误判成负号）
    nums = [int(round(float(n))) for n in re.findall(r"\d+", str(s))]
    if len(nums) >= 3:
        return f"{nums[0]}-{nums[1]}-{nums[2]}"
    if len(nums) == 2:
        return f"{nums[0]}-{nums[1]}-145"
    return "52-18-145"


def write_csv(rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    logger.info("已写入 %s (%d 条)", CSV_PATH, len(rows))


def generate_svgs(rows: list[dict]) -> int:
    from generate_glasses_data import make_svg

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in rows:
        if not str(r.get("image_url", "")).strip().endswith(".svg"):
            continue
        svg = make_svg(r["frame_shape"], r.get("frame_material"))
        (IMG_DIR / f"{r['glasses_id']}.svg").write_text(svg, encoding="utf-8")
        n += 1
    logger.info("已生成 %d 张 SVG 占位图", n)
    return n


def resync_sqlite() -> None:
    """清空眼镜表并补全 name/brand 列，使后端下次启动从新 CSV 重新种子。"""
    db_path = Path(DB_PATH)
    if not db_path.exists():
        logger.warning("%s 不存在，跳过 SQLite 重刷（首次启动会自动建表）", db_path)
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cols = {r[1] for r in cur.execute("PRAGMA table_info(glasses)")}
    for c in ("name", "brand"):
        if c not in cols:
            cur.execute(f"ALTER TABLE glasses ADD COLUMN {c} VARCHAR(120)")
            logger.info("SQLite glasses 表补充列 %s", c)
    cur.execute("DELETE FROM glasses")
    conn.commit()
    conn.close()
    logger.info("已清空 SQLite glasses 表，重启后端即按新 CSV 重新种子")


def main() -> int:
    ap = argparse.ArgumentParser(description="导入真实眼镜商品数据")
    ap.add_argument("source", help="源文件 .csv / .xlsx")
    ap.add_argument("--resync", action="store_true", help="重刷 SQLite 商城库")
    ap.add_argument("--no-svg", action="store_true", help="不为缺失图片的条目生成 SVG")
    args = ap.parse_args()

    src = Path(args.source)
    if not src.exists():
        logger.error("源文件不存在: %s", src)
        return 2

    try:
        headers, raw = read_source(src)
    except Exception as e:
        logger.error("读取失败: %s", e)
        return 2

    logger.info("读取到 %d 行，表头: %s", len(raw), headers)
    rows = transform(headers, raw)
    if not rows:
        logger.error("没有可导入的有效行")
        return 1

    write_csv(rows)
    if not args.no_svg:
        generate_svgs(rows)
    if args.resync:
        resync_sqlite()
        logger.info("==> 请重启 后端(5000) 与 模型服务(8000) 以加载新数据")

    dist = {}
    for r in rows:
        dist[r["frame_shape"]] = dist.get(r["frame_shape"], 0) + 1
    logger.info("导入完成：%d 款，框型分布 %s", len(rows), dist)
    return 0


if __name__ == "__main__":
    sys.exit(main())
