"""
在现有 manifest 基础上，追加下载指定的 Wikimedia Commons 文件（用于补充现代框型）。

用法:
    python tools/add_specific_commons_files.py \
        "Cat eye sunglasses.jpg" \
        "Hans Anders sunglasses, Winschoten (2019) 01.jpg" \
        "Mezmay, Sports sunglasses, Black sunglasses, Russia.jpg"
"""
import csv
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE_DIR = ROOT / "data" / "glasses_images"
MANIFEST = ROOT / "data" / "glasses_images_manifest.csv"

API = "https://commons.wikimedia.org/w/api.php"
UA = "DanzhiHuiyan-Glasses-Recommender/1.0 (college-project; local-contact)"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def existing_max_id():
    if not MANIFEST.exists():
        return 0
    with MANIFEST.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    nums = []
    for r in rows:
        m = re.match(r"G(\d{3})", r.get("id", ""))
        if m:
            nums.append(int(m.group(1)))
    return max(nums, default=0)


def api_get(params, timeout=25):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.load(r)


def metadata_value(info, key):
    em = info.get("extmetadata", {})
    if key in em and isinstance(em[key], dict):
        return em[key].get("value", "") or ""
    return ""


def download(url, dest, timeout=30, max_retries=8):
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
                time.sleep(2 + attempt * 2)
                continue
            print(f"  HTTP {e.code} for {dest.name}")
            return False
        except Exception as e:
            print(f"  {dest.name}: {e}")
            return False
    return False


def main():
    if len(sys.argv) < 2:
        print("用法: python tools/add_specific_commons_files.py \"File1.jpg\" \"File2.jpg\" ...")
        return

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    existing = []
    if MANIFEST.exists():
        with MANIFEST.open(encoding="utf-8") as f:
            existing = list(csv.DictReader(f))

    start = existing_max_id()
    titles = [t if t.startswith("File:") else f"File:{t}" for t in sys.argv[1:]]
    params = {
        "action": "query",
        "titles": "|".join(titles),
        "prop": "imageinfo",
        "iiprop": "url|mime|thumburl|size|extmetadata",
        "iiurlwidth": 800,
        "format": "json",
    }
    data = api_get(params)
    pages = data.get("query", {}).get("pages", {})

    new_rows = []
    for pid, page in pages.items():
        title = page.get("title", "")
        ii = page.get("imageinfo", [])
        if not ii:
            print(f"[skip] no info: {title}")
            continue
        info = ii[0]
        mime = info.get("mime", "")
        if mime not in ("image/jpeg", "image/png"):
            print(f"[skip] not image: {title}")
            continue
        thumb = info.get("thumburl") or info.get("url")
        if not thumb:
            print(f"[skip] no url: {title}")
            continue

        start += 1
        fid = f"G{start:03d}"
        dest = IMAGE_DIR / f"{fid}.jpg"
        if download(thumb, dest):
            author = metadata_value(info, "Artist") or metadata_value(info, "Credit") or ""
            author = re.sub(r"<[^>]+>", "", author).strip()
            license_name = metadata_value(info, "LicenseShortName") or "unknown"
            license_url = metadata_value(info, "LicenseUrl") or ""
            new_rows.append({
                "id": fid,
                "file": f"{fid}.jpg",
                "title": title.replace("File:", "").strip(),
                "author": author,
                "license": license_name,
                "license_url": license_url,
                "source_url": info.get("url", ""),
                "width": info.get("width", 0),
                "height": info.get("height", 0),
            })
            print(f"[ok] {fid} <- {license_name} | {title[:55]}")
        time.sleep(1.5)

    if new_rows:
        all_rows = existing + new_rows
        with MANIFEST.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "file", "title", "author", "license", "license_url", "source_url", "width", "height"])
            w.writeheader()
            w.writerows(all_rows)
        print(f"\n追加 {len(new_rows)} 张，当前共 {len(all_rows)} 张")
    else:
        print("无新增")


if __name__ == "__main__":
    main()
