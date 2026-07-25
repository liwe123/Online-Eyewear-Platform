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

STROKE = "#1a1a2e"


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

def _rim_elements(shape: str) -> str:
    """返回两个镜圈的 SVG 元素（左圈中心约 (95,90)，右圈约 (205,90)）"""
    common = f'fill="none" stroke="{STROKE}" stroke-width="6" stroke-linejoin="round"'
    if shape == "方形":
        return (
            f'<rect x="63" y="64" width="64" height="52" rx="10" {common}/>'
            f'<rect x="173" y="64" width="64" height="52" rx="10" {common}/>'
        )
    if shape == "圆形":
        return (
            f'<circle cx="95" cy="90" r="28" {common}/>'
            f'<circle cx="205" cy="90" r="28" {common}/>'
        )
    if shape == "长方形":
        return (
            f'<rect x="61" y="72" width="68" height="38" rx="5" {common}/>'
            f'<rect x="171" y="72" width="68" height="38" rx="5" {common}/>'
        )
    if shape == "鹅蛋形":
        return (
            f'<ellipse cx="95" cy="90" rx="34" ry="25" {common}/>'
            f'<ellipse cx="205" cy="90" rx="34" ry="25" {common}/>'
        )
    if shape == "多边形":  # 六边形
        return (
            f'<polygon points="95,62 119,76 119,104 95,118 71,104 71,76" {common}/>'
            f'<polygon points="205,62 229,76 229,104 205,118 181,104 181,76" {common}/>'
        )
    if shape == "猫眼形":  # 外上角上挑
        return (
            f'<path d="M 125 88 C 126 105 110 114 95 114 C 76 114 68 104 68 92 '
            f'C 68 82 58 74 52 66 C 66 68 80 70 95 72 C 112 74 124 78 125 88 Z" {common}/>'
            f'<path d="M 175 88 C 174 105 190 114 205 114 C 224 114 232 104 232 92 '
            f'C 232 82 242 74 248 66 C 234 68 220 70 205 72 C 188 74 176 78 175 88 Z" {common}/>'
        )
    raise ValueError(f"未知形状: {shape}")


def make_svg(shape: str) -> str:
    rims = _rim_elements(shape)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200" viewBox="0 0 300 200">\n'
        '  <rect width="300" height="200" fill="#f0f0f0"/>\n'
        f'  {rims}\n'
        # 中梁
        f'  <path d="M 126 86 Q 150 72 174 86" fill="none" stroke="{STROKE}" stroke-width="6" stroke-linecap="round"/>\n'
        # 镜腿线条
        f'  <path d="M 64 84 L 28 62" fill="none" stroke="{STROKE}" stroke-width="6" stroke-linecap="round"/>\n'
        f'  <path d="M 236 84 L 272 62" fill="none" stroke="{STROKE}" stroke-width="6" stroke-linecap="round"/>\n'
        f'  <text x="150" y="184" text-anchor="middle" font-family="sans-serif" font-size="20" fill="{STROKE}">{shape}</text>\n'
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
        svg = make_svg(row["frame_shape"])
        (IMG_DIR / f"{row['glasses_id']}.svg").write_text(svg, encoding="utf-8")

    # 汇总输出
    dist = {s: sum(1 for r in rows if r["frame_shape"] == s) for s in SHAPES}
    print(f"CSV 写入: {CSV_PATH} ({len(rows)} 条)")
    print(f"SVG 写入: {IMG_DIR} ({len(rows)} 张)")
    print(f"形状分布: {dist}")


if __name__ == "__main__":
    main()
