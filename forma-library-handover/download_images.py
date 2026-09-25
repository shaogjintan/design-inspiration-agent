"""Download every Forma library image into ./images, named by library ID.

Usage (Python 3.8+, no extra packages needed):
    python3 download_images.py            # 1080px wide copies
    python3 download_images.py --thumbs   # 400px wide copies instead

Run it from the folder that holds forma-library.json.
"""
import json
import pathlib
import sys
import time
import urllib.request

thumbs = "--thumbs" in sys.argv
lib = json.loads(pathlib.Path("forma-library.json").read_text(encoding="utf-8"))
out = pathlib.Path("images_thumbs" if thumbs else "images")
out.mkdir(exist_ok=True)

failed = []
for rec in lib["images"]:
    url = rec["image"]["thumb_url" if thumbs else "url"]
    dest = out / f"{rec['id']}.jpg"
    if dest.exists() and dest.stat().st_size > 0:
        continue
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "forma-library-downloader"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest.write_bytes(resp.read())
        print(f"ok   {rec['id']}")
    except Exception as exc:  # keep going, report at the end
        failed.append((rec["id"], str(exc)))
        print(f"FAIL {rec['id']}  {exc}")
    time.sleep(0.2)

print(f"\nSaved {len(lib['images']) - len(failed)} of {len(lib['images'])} images to ./{out}")
if failed:
    print("Failed IDs:", ", ".join(i for i, _ in failed))
