"""
从 Wikimedia Commons 搜索博物馆/藏品级真实眼镜照片，落地到 data/glasses_images/。

搜索策略（针对静物/藏品照片，避开人像和书页扫描）：
- Eyeglasses (AM ... / MET ... / Case And Eyeglasses ... / Lunettes ... / Brille ... / Bifokalbrille
- Okulary korekcyjne / Reading glasses / 1950sGlasses / Old glasses

过滤：
- 仅 jpeg/png，宽>=500
- 标题含 portrait/woman/man/selfie/fig/affiche/programme/pdf/djvu 等跳过
- 检测到 429 时主动退让并限量重试

输出 manifest：id,file,title,author,license,license_url,source_url,width,height

用法:
    python tools/fetch_real_glasses_images.py --limit 36
"""
import argparse
import csv
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE_DIR = ROOT / "data" / "glasses_images"
MANIFEST = ROOT / "data" / "glasses_images_manifest.csv"

API = "https://commons.wikimedia.org/w/api.php"

SEARCH_TERMS = [
    # 博物馆静物（高优先级）
    ("Eyeglasses (AM", 3),
    ("Glasses (AM", 2),
    ("Eyeglasses MET", 2),
    ("Spectacles MET", 1),
    ("Case And Eyeglasses", 2),
    ("Lunettes de", 1),
    ("Bril met ronde glazen", 1),
    ("Bifokalbrille", 1),
    ("Okulary korekcyjne", 1),
    # 现代/阅读镜
    ("Reading glasses", 2),
    ("Old glasses", 1),
    ("1950sGlasses", 1),
]

# 标题过滤：看到就跳过（不区分大小写）
SKIP_TITLE_RE = re.compile(
    r"\b(svg|pdf|djvu|map|chart|signature|logo|seal|coat of arms|flag|emblem|"
    r"selfie|portrait|bust|headshot|wedding|graduation|affiche|poster|programme|"
    r"newspaper|book|magazine|page|fig\.?|figure|plate|engraving|illustration|"
    r"woman in|man in|women in|men in|wearing|wears|laboratory|store interior|"
    r"tanner|at work|in her|in his|shown in|painting|by .*dantan|gandhi|"
    r"histology|microscope|medical|x-ray|radiograph|fundus|retina|nebula|galaxy|"
    r"planet|mars|jupiter|sun)\b",
    re.IGNORECASE,
)

UA = "DanzhiHuiyan-Glasses-Recommender/1.0 (college-project; local-contact)"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def api_get(params: dict, timeout=25) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.load(r)


def search_files(term: str, limit: int, offset: int = 0):
    params = {
        "action": "query",
        "list": "search",
        "srnamespace": 6,
        "srsearch": term,
        "srlimit": min(limit, 50),
        "sroffset": offset,
        "format": "json",
    }
    data = api_get(params)
    return data.get("query", {}).get("search", [])


def get_image_info(titles: list[str]) -> dict:
    joined = "|".join(titles)
    params = {
        "action": "query",
        "titles": joined,
        "prop": "imageinfo",
        "iiprop": "url|mime|thumburl|size|extmetadata",
        "iiurlwidth": 800,
        "format": "json",
    }
    data = api_get(params)
    result = {}
    for pid, page in data.get("query", {}).get("pages", {}).items():
        ii = page.get("imageinfo", [])
        if ii:
            result[page.get("title", "")] = ii[0]
    return result


def metadata_value(info: dict, key: str) -> str:
    em = info.get("extmetadata", {})
    if key in em and isinstance(em[key], dict):
        return em[key].get("value", "") or ""
    return ""


def download_with_retry(url: str, dest: Path, timeout=30, max_retries=8) -> bool:
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                data = r.read()
            if len(data) < 3000:
                return False
            dest.write_bytes(data)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                sleep = 2 + attempt * 2
                print(f"  [429] {dest.name} attempt {attempt+1}/{max_retries}, sleep {sleep}s")
                time.sleep(sleep)
                continue
            print(f"  [warn] HTTP {e.code} for {dest.name}")
            return False
        except Exception as e:
            print(f"  [warn] {dest.name}: {e}")
            return False
    print(f"  [warn] {dest.name}: 429 retries exhausted")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=36)
    args = ap.parse_args()

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    seen_titles = set()
    idx = 1

    for term, max_pages in SEARCH_TERMS:
        if len(rows) >= args.limit:
            break
        offset = 0
        for _ in range(max_pages):
            if len(rows) >= args.limit:
                break
            need = min(50, args.limit - len(rows) + 10)  # 多要一些给过滤留余量
            try:
                hits = search_files(term, need, offset)
            except Exception as e:
                print(f"[warn] search '{term}' offset {offset}: {e}")
                break
            if not hits:
                break
            offset += len(hits)

            titles = [h["title"] for h in hits if h["title"] not in seen_titles]
            if not titles:
                continue

            try:
                info_map = get_image_info(titles)
            except Exception as e:
                print(f"[warn] imageinfo for '{term}': {e}")
                continue

            for title in titles:
                if len(rows) >= args.limit:
                    break
                if title in seen_titles:
                    continue
                seen_titles.add(title)
                info = info_map.get(title)
                if not info:
                    continue

                if SKIP_TITLE_RE.search(title):
                    continue

                mime = info.get("mime", "")
                if mime not in ("image/jpeg", "image/png"):
                    continue
                width = info.get("width", 0) or 0
                if width < 500:
                    continue

                thumb = info.get("thumburl") or info.get("url")
                if not thumb:
                    continue

                author = metadata_value(info, "Artist") or metadata_value(info, "Credit") or ""
                license_name = metadata_value(info, "LicenseShortName") or "unknown"
                license_url = metadata_value(info, "LicenseUrl") or ""
                author = re.sub(r"<[^>]+>", "", author).strip()

                fid = f"G{idx:03d}"
                dest = IMAGE_DIR / f"{fid}.jpg"
                if download_with_retry(thumb, dest):
                    rows.append({
                        "id": fid,
                        "file": f"{fid}.jpg",
                        "title": title.replace("File:", "").strip(),
                        "author": author,
                        "license": license_name,
                        "license_url": license_url,
                        "source_url": info.get("url", ""),
                        "width": width,
                        "height": info.get("height", 0),
                    })
                    print(f"[ok] {fid} <- {license_name} | {title[:55]}")
                    idx += 1
                time.sleep(1.5)  # 礼貌限速，降低 429

    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "file", "title", "author", "license", "license_url", "source_url", "width", "height"])
        w.writeheader()
        w.writerows(rows)

    print(f"\n完成：成功下载 {len(rows)} 张，manifest -> {MANIFEST}")


if __name__ == "__main__":
    main()
