"""
把已下载的眼镜图拼成可标注的网格图（contact sheet）。

每格仅显示图片 + 商品ID，便于人工看图判定框型。
输出到 data/contact_sheets/sheet_NNN.png，每页 9 张（3x3）。

用法:
    python tools/make_contact_sheets.py            # 全部，每页9张
    python tools/make_contact_sheets.py --per 9 --cols 3
"""
import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
IMAGE_DIR = ROOT / "data" / "glasses_images"
MANIFEST = ROOT / "data" / "glasses_images_manifest.csv"
OUT = ROOT / "data" / "contact_sheets"
OUT.mkdir(parents=True, exist_ok=True)

THUMB = 320
PAD = 8
LABEL_H = 34


def load_manifest():
    rows = []
    with MANIFEST.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def get_font(size):
    for p in [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def make_sheet(items, cols, font):
    rows = (len(items) + cols - 1) // cols
    W = cols * (THUMB + PAD) + PAD
    H = rows * (THUMB + LABEL_H + PAD) + PAD
    sheet = Image.new("RGB", (W, H), (240, 240, 240))
    d = ImageDraw.Draw(sheet)
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x = PAD + c * (THUMB + PAD)
        y = PAD + r * (THUMB + LABEL_H + PAD)
        img_path = IMAGE_DIR / it["file"]
        try:
            im = Image.open(img_path).convert("RGB")
            im.thumbnail((THUMB, THUMB))
            ox = x + (THUMB - im.width) // 2
            oy = y + (THUMB - im.height) // 2
            sheet.paste(im, (ox, oy))
        except Exception as e:
            d.text((x + 4, y + THUMB // 2), f"ERR {it['file']}", fill=(200, 0, 0), font=font)
        d.rectangle([x, y, x + THUMB, y + THUMB], outline=(120, 120, 120), width=1)
        label = it["id"]
        d.text((x + 4, y + THUMB + 4), label, fill=(20, 20, 20), font=font)
    return sheet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=9)
    ap.add_argument("--cols", type=int, default=3)
    args = ap.parse_args()

    rows = load_manifest()
    if not rows:
        print("manifest 为空，先跑 fetch_real_glasses_images.py")
        return

    font = get_font(18)
    n = 0
    for i in range(0, len(rows), args.per):
        batch = rows[i:i + args.per]
        sheet = make_sheet(batch, args.cols, font)
        out = OUT / f"sheet_{n:03d}.png"
        sheet.save(out)
        print(f"[ok] {out}  ({len(batch)} 张)")
        n += 1
    print(f"\n共生成 {n} 张拼图，位于 {OUT}")


if __name__ == "__main__":
    main()
