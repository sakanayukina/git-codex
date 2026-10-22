# Pick a CC0 ground-diffuse texture from Poly Haven and convert it to PNG.
# Usage: python fetch_texture.py forest_floor 4k
import io
import json
import os
import sys
import urllib.request

from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}


def get(u, raw=False):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=180) as r:
        return r.read() if raw else json.load(r)


want = sys.argv[1] if len(sys.argv) > 1 else "forest_floor"
res = sys.argv[2] if len(sys.argv) > 2 else "1k"

assets = get("https://api.polyhaven.com/assets?t=textures")
hits = [t for t in assets if want in t]
print("matches:", hits[:5])
if not hits:
    raise SystemExit(1)
tid = hits[0]

files = get(f"https://api.polyhaven.com/files/{tid}")
resolved = res
for r in (res, "2k", "1k"):
    if r in files.get("Diffuse", {}):
        resolved = r
        break
diff = files["Diffuse"][resolved]["jpg"]

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tex")
os.makedirs(out, exist_ok=True)
png_path = os.path.join(out, f"{tid}_diffuse.png")
raw = get(diff["url"], raw=True)
img = Image.open(io.BytesIO(raw)).convert("RGB")
img.save(png_path)
print("wrote", png_path, img.size, "(source", resolved + ")")
