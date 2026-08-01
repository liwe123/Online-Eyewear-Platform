# -*- coding: utf-8 -*-
"""用 rembg 为所有眼镜产品生成透明 PNG 试戴素材（一次性开发工具）。

输入: data/glasses_data.csv 的 image_url（如 /static/glasses/G001.jpg）
输出: data/glasses_images/tryon/<glasses_id>.png（RGBA，背景已去除）

首次运行会自动下载 U2Net 模型（~170MB）。仅开发期使用：生成的 PNG 入库后，
运行时与 CI 都不依赖 rembg。已存在且不早于源图的输出会跳过（幂等）。

注意：rembg 依赖 numpy 2.x，与项目运行时（pandas 2.1.4 要求 numpy<2）冲突，
必须在独立 venv 中运行，勿装进项目 .venv。示例：
  python -m venv <临时目录>/dzhy_tryon_venv
  <临时目录>/dzhy_tryon_venv/Scripts/pip install "rembg[cpu]"
  <临时目录>/dzhy_tryon_venv/Scripts/python tools/make_tryon_overlays.py
"""
from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

logger = logging.getLogger("make_tryon_overlays")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CSV_PATH = DATA_DIR / "glasses_data.csv"
IMAGES_DIR = DATA_DIR / "glasses_images"
OUTPUT_DIR = IMAGES_DIR / "tryon"


def load_catalog() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    items = load_catalog()
    logger.info(f"共 {len(items)} 款眼镜，输出目录: {OUTPUT_DIR}")

    try:
        import numpy as np
        from PIL import Image
        from rembg import new_session, remove
    except ImportError as exc:
        logger.error(f"缺少依赖（{exc}），请先执行: .venv/Scripts/python -m pip install rembg")
        return 1

    # 复用同一个 session，避免每张图重建模型
    session = new_session("u2net")

    ok = skipped = failed = 0
    for item in items:
        gid = item["glasses_id"]
        src = IMAGES_DIR / Path(item["image_url"]).name  # /static/glasses/G001.jpg -> G001.jpg
        out = OUTPUT_DIR / f"{gid}.png"
        if not src.exists():
            logger.warning(f"{gid}: 源图不存在 {src}，跳过")
            failed += 1
            continue
        if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
            skipped += 1
            continue
        try:
            img = np.asarray(Image.open(src).convert("RGB"))
            result = remove(img, session=session, post_process_mask=True)
            rgba = Image.fromarray(result)
            # 裁剪到不透明区域：去掉空边距（叠加以图像中心定位，紧裁更准），
            # 同时清理可能残留的边缘背景
            mask = rgba.getchannel("A").point(lambda v: 255 if v > 10 else 0)
            bbox = mask.getbbox()
            if bbox:
                rgba = rgba.crop(bbox)
            rgba.save(out)
            ok += 1
            logger.info(f"{gid}: 已生成 {out.name}")
        except Exception as exc:
            logger.warning(f"{gid}: 抠图失败: {exc}")
            failed += 1

    logger.info(f"完成: 生成 {ok}，跳过 {skipped}，失败 {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
