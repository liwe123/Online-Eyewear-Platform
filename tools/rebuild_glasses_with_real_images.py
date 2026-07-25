"""
用已下载的真实眼镜图 + 人工框型标注 + Commons 元数据，重建 data/glasses_data.csv。

流程：
1. 必须先有人工标注文件 data/glasses_labels.csv（id,frame_shape）。
2. 读取 data/glasses_images_manifest.csv（title/author/license/source_url）。
3. 按标注框型补全商品字段（品牌/尺寸/材质/度数/折射率/价格/中文名）。
4. 生成 data/glasses_data.csv 作为后端+模型服务的商品库来源。
5. 生成 data/glasses_attribution.csv 保留 CC/来源署名。

受控框型词表（与 recommend_rules.FACE_FRAME_MAP 对齐）：
    圆形 / 鹅蛋形 / 猫眼形 / 方形 / 长方形 / 多边形

用法:
    # 先人工标注：看图后在 data/glasses_labels.csv 写入 id,frame_shape
    python tools/rebuild_glasses_with_real_images.py
"""
import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MANIFEST = DATA / "glasses_images_manifest.csv"
LABELS = DATA / "glasses_labels.csv"
OUT_CSV = DATA / "glasses_data.csv"
ATTR_CSV = DATA / "glasses_attribution.csv"

VALID_SHAPES = {"圆形", "鹅蛋形", "猫眼形", "方形", "长方形", "多边形"}

SHAPE_PROFILE = {
    "圆形":   ("50-20-140", ["合金", "纯钛", "TR90"], "圆框光学镜"),
    "鹅蛋形": ("52-18-145", ["纯钛", "板材", "β钛"], "鹅蛋框光学镜"),
    "猫眼形": ("51-18-140", ["板材", "TR90", "合金"], "猫眼框光学镜"),
    "方形":   ("52-18-145", ["板材", "纯钛", "金属"], "方框光学镜"),
    "长方形": ("54-18-148", ["纯钛", "金属", "TR90"], "长方框光学镜"),
    "多边形": ("55-19-148", ["金属", "纯钛", "合金"], "多边形飞行员镜"),
}

BRANDS = ["明视光学", "睛典", "视界工坊", "眸光", "睐卡", "酷视"]
INDICES = [1.60, 1.67, 1.74]


def load_csv(path: Path, required=False) -> list[dict]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"必需文件缺失: {path}")
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    labels = {r["id"].strip(): r["frame_shape"].strip() for r in load_csv(LABELS, required=True)}
    bad = {k: v for k, v in labels.items() if v not in VALID_SHAPES}
    if bad:
        print(f"[error] 以下框型不在受控词表 {VALID_SHAPES}: {bad}")
        return

    manifest = load_csv(MANIFEST, required=True)
    if not manifest:
        print("[error] manifest 为空")
        return

    random.seed(42)
    out_rows = []
    attr_rows = []
    for it in manifest:
        gid = it["id"]
        shape = labels.get(gid)
        if shape is None:
            print(f"[warn] {gid} 未标注，跳过")
            continue
        size, materials, name_suffix = SHAPE_PROFILE[shape]
        brand = random.choice(BRANDS)
        material = random.choice(materials)
        index = random.choice(INDICES)
        base = {"纯钛": 599, "β钛": 659, "板材": 359, "TR90": 299,
                "金属": 399, "合金": 269}.get(material, 399)
        price = base + INDICES.index(index) * 120 + random.randint(-30, 60)
        price = max(199, round(price / 10) * 10)
        name = f"{brand} {name_suffix}"

        out_rows.append({
            "glasses_id": gid,
            "name": name,
            "brand": brand,
            "frame_shape": shape,
            "frame_size": size,
            "frame_material": material,
            "lens_degree_min": -8.00,
            "lens_degree_max": -0.25,
            "lens_refractive_index": index,
            "price": price,
            "image_url": f"/static/glasses/{it['file']}",
        })
        attr_rows.append({
            "id": gid,
            "file": it["file"],
            "title": it["title"],
            "author": it["author"],
            "license": it["license"],
            "license_url": it["license_url"],
            "source_url": it["source_url"],
        })

    if not out_rows:
        print("[error] 没有可写入的商品行")
        return

    fields = ["glasses_id", "name", "brand", "frame_shape", "frame_size",
              "frame_material", "lens_degree_min", "lens_degree_max",
              "lens_refractive_index", "price", "image_url"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    with ATTR_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["id", "file", "title", "author", "license", "license_url", "source_url"])
        w.writeheader()
        w.writerows(attr_rows)

    from collections import Counter
    dist = Counter(r["frame_shape"] for r in out_rows)
    print(f"[ok] 商品库 {len(out_rows)} 条 -> {OUT_CSV}")
    print(f"[ok] 署名清单 -> {ATTR_CSV}")
    print(f"[分布] {dict(dist)}")


if __name__ == "__main__":
    main()
