# -*- coding: utf-8 -*-
"""丹智慧眼 - 商品数据生成器

生成 48 条真实感眼镜数据到 data/glasses_data.csv，
并为每款眼镜生成一张 SVG 占位图到 data/glasses_images/。

直接运行: python tools/generate_glasses_data.py
幂等: 固定随机种子，可重复执行，产出完全一致。
"""
import csv
import random
from pathlib import Path

# 固定种子，保证幂等
random.seed(42)

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
IMG_DIR = DATA_DIR / "glasses_images"
CSV_PATH = DATA_DIR / "glasses_data.csv"

TOTAL = 48
SHAPES = ["方形", "圆形", "猫眼形", "长方形", "鹅蛋形", "多边形"]  # 各 8 款
MATERIALS = ["TR90", "纯钛", "板材", "金属", "钛合金", "复合板材"]
# (lens_degree_min, lens_degree_max) 候选范围
DEGREE_RANGES = [(-12.0, -1.0), (-10.0, -0.5), (-8.0, -0.5), (-6.0, -0.25)]
# 材质价格分档
PRICE_TIERS = {
    "纯钛": (599, 1299),
    "钛合金": (599, 1299),
    "金属": (399, 899),
    "复合板材": (399, 899),
    "TR90": (199, 599),
    "板材": (199, 599),
}

# 镜框描边/底色：按材质着色，让占位图更接近真实镜框观感
STROKE = "#1a1a2e"
MATERIAL_COLORS: dict[str, str] = {
    "纯钛": "#BFC0C8",
    "钛合金": "#CACBD2",
    "金属": "#D4AF37",
    "合金": "#C2C2CC",
    "板材": "#2E2E2E",
    "复合板材": "#3C3C3C",
    "TR90": "#3FA7D6",
}
DEFAULT_COLOR = "#444455"


def pick_refractive_index(degree_min: float) -> float:
    """高度数偏向高折射率"""
    a = abs(degree_min)
    if a >= 10:
        return random.choices([1.60, 1.67, 1.74], weights=[1, 3, 6])[0]
    if a >= 8:
        return random.choices([1.56, 1.60, 1.67, 1.74], weights=[1, 3, 4, 2])[0]
    return random.choices([1.56, 1.60, 1.67], weights=[5, 3, 2])[0]


def pick_price(material: str) -> int:
    lo, hi = PRICE_TIERS[material]
    p = random.randint(lo, hi)
    # 价格取 x9 结尾（如 299/599），并夹在档位区间内
    return max(lo, min(hi, p // 10 * 10 + 9))


def make_frame_size() -> str:
    width = random.randint(48, 56)   # 镜宽
    bridge = random.randint(16, 21)  # 鼻梁
    temple = random.randint(138, 148)  # 镜腿
    return f"{width}-{bridge}-{temple}"


# ---------------------------------------------------------------------------
# SVG 占位图绘制：300x200，浅灰底，两个镜圈 + 中梁 + 镜腿线条
# ---------------------------------------------------------------------------

def _rim_element(shape: str, cx: float, cy: float, color: str) -> str:
    """单个镜圈的 SVG 元素，中心 (cx, cy)；按材质着色并带内描边高光。"""
    rim = f'fill="{color}" fill-opacity="0.18" stroke="{STROKE}" stroke-width="5" stroke-linejoin="round"'
    inner = f'fill="none" stroke="{STROKE}" stroke-width="2" stroke-opacity="0.35"'
    if shape == "方形":
        return (f'<rect x="{cx-30}" y="{cy-25}" width="60" height="50" rx="9" {rim}/>'
                f'<rect x="{cx-30}" y="{cy-25}" width="60" height="50" rx="9" {inner}/>')
    if shape == "圆形":
        return (f'<circle cx="{cx}" cy="{cy}" r="28" {rim}/>'
                f'<circle cx="{cx}" cy="{cy}" r="28" {inner}/>')
    if shape == "长方形":
        return (f'<rect x="{cx-32}" y="{cy-20}" width="64" height="40" rx="6" {rim}/>'
                f'<rect x="{cx-32}" y="{cy-20}" width="64" height="40" rx="6" {inner}/>')
    if shape == "鹅蛋形":
        return (f'<ellipse cx="{cx}" cy="{cy}" rx="33" ry="26" {rim}/>'
                f'<ellipse cx="{cx}" cy="{cy}" rx="33" ry="26" {inner}/>')
    if shape == "多边形":  # 六边形
        pts = (f"{cx},{cy-30} {cx+26},{cy-15} {cx+26},{cy+15} {cx},{cy+30} "
               f"{cx-26},{cy+15} {cx-26},{cy-15}")
        return (f'<polygon points="{pts}" {rim}/>'
                f'<polygon points="{pts}" {inner}/>')
    if shape == "猫眼形":  # 外上角上挑
        d = (f'M {cx-30} {cy+18} C {cx-31} {cy+2} {cx-18} {cy-8} {cx} {cy-9} '
             f'C {cx+18} {cy-10} {cx+31} {cy+2} {cx+30} {cy+18} '
             f'C {cx+27} {cy-6} {cx+10} {cy-14} {cx} {cy-12} '
             f'C {cx-12} {cy-14} {cx-28} {cy-6} {cx-30} {cy+18} Z')
        return f'<path d="{d}" {rim}/>'
    raise ValueError(f"未知形状: {shape}")


def make_svg(shape: str, material: str | None = None) -> str:
    color = MATERIAL_COLORS.get((material or "").strip(), DEFAULT_COLOR)
    left = _rim_element(shape, 95, 100, color)
    right = _rim_element(shape, 205, 100, color)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200" viewBox="0 0 300 200">\n'
        '  <defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#fafafa"/><stop offset="1" stop-color="#eceef2"/></linearGradient></defs>\n'
        '  <rect width="300" height="200" fill="url(#bg)"/>\n'
        # 镜腿
        f'  <path d="M 65 96 L 26 70" fill="none" stroke="{STROKE}" stroke-width="5" stroke-linecap="round"/>\n'
        f'  <path d="M 235 96 L 274 70" fill="none" stroke="{STROKE}" stroke-width="5" stroke-linecap="round"/>\n'
        # 铰链点
        f'  <circle cx="66" cy="96" r="3.5" fill="{STROKE}"/>\n'
        f'  <circle cx="234" cy="96" r="3.5" fill="{STROKE}"/>\n'
        # 中梁
        f'  <path d="M 126 92 Q 150 80 174 92" fill="none" stroke="{STROKE}" stroke-width="5" stroke-linecap="round"/>\n'
        # 鼻托
        f'  <path d="M 138 104 q -4 8 -1 14" fill="none" stroke="{STROKE}" stroke-width="2.5" stroke-opacity="0.6"/>\n'
        f'  <path d="M 162 104 q 4 8 1 14" fill="none" stroke="{STROKE}" stroke-width="2.5" stroke-opacity="0.6"/>\n'
        f'  {left}\n'
        f'  {right}\n'
        f'  <text x="150" y="190" text-anchor="middle" font-family="sans-serif" font-size="16" fill="{STROKE}">{shape}</text>\n'
        '</svg>\n'
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def build_rows() -> list[dict]:
    # 每种形状恰好 8 款，打乱顺序分布到 G001~G048
    shape_pool = [s for s in SHAPES for _ in range(TOTAL // len(SHAPES))]
    random.shuffle(shape_pool)

    rows = []
    for i in range(TOTAL):
        gid = f"G{i + 1:03d}"
        shape = shape_pool[i]
        material = random.choice(MATERIALS)
        dmin, dmax = random.choice(DEGREE_RANGES)
        rows.append({
            "glasses_id": gid,
            "frame_shape": shape,
            "frame_size": make_frame_size(),
            "frame_material": material,
            "lens_degree_min": f"{dmin:.2f}",
            "lens_degree_max": f"{dmax:.2f}",
            "lens_refractive_index": pick_refractive_index(dmin),
            "price": pick_price(material),
            "image_url": f"/static/glasses/{gid}.svg",
        })
    return rows


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    # 幂等：先清理旧的 G*.svg，再重新生成
    for old in IMG_DIR.glob("G*.svg"):
        old.unlink()

    rows = build_rows()

    fieldnames = ["glasses_id", "frame_shape", "frame_size", "frame_material",
                  "lens_degree_min", "lens_degree_max", "lens_refractive_index",
                  "price", "image_url"]
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    for row in rows:
        svg = make_svg(row["frame_shape"], row["frame_material"])
        (IMG_DIR / f"{row['glasses_id']}.svg").write_text(svg, encoding="utf-8")

    # 汇总输出
    dist = {s: sum(1 for r in rows if r["frame_shape"] == s) for s in SHAPES}
    print(f"CSV 写入: {CSV_PATH} ({len(rows)} 条)")
    print(f"SVG 写入: {IMG_DIR} ({len(rows)} 张)")
    print(f"形状分布: {dist}")


if __name__ == "__main__":
    main()
