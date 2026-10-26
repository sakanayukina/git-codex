r"""Fetch real terrain elevation (Terrarium PNG tiles) and export MuJoCo heightfields.

No GDAL / rasterio needed: AWS 'elevation-tiles-prod' Terrarium tiles are plain PNGs,
elevation (m) = R*256 + G + B/256 - 32768.

AWS serves zooms 0..15 only (~4.1 m/px at lat 31), so pick patch size accordingly:
200-400 m scenes are the sweet spot; asking for 20 m just upsamples a 5x5 grid.

Usage:
    python fetch_dem.py --lat 31.055 --lon 103.483 --half 100 --px 128 --out ..\terrain\dem_200m.png
"""
import argparse
import io
import math
import os
import urllib.request

import numpy as np
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
EARTH_R = 6378137.0
TILE_PX = 256
TILE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tiles")


def deg2num(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def num2deg(x, y, z):
    n = 2 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def mpp(lat, z):
    """Metres per pixel of a slippy tile at given latitude."""
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** z)


def fetch_tile(z, x, y):
    path = os.path.join(TILE_CACHE, str(z), str(x), f"{y}.png")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return Image.open(io.BytesIO(f.read())).convert("RGB")
    url = TILE_URL.format(z=z, x=x, y=y)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        blob = r.read()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(blob)
    return Image.open(io.BytesIO(blob)).convert("RGB")


def terrain_value(tile):
    a = np.asarray(tile, dtype=np.float64)
    return a[:, :, 0] * 256.0 + a[:, :, 1] + a[:, :, 2] / 256.0 - 32768.0


def sample(z, half_m, lat, lon):
    """Return (heights_metres, extent_m) of a square patch centred on lat/lon."""
    cx, cy = deg2num(lat, lon, z)
    m = mpp(lat, z)
    half_px = half_m / m
    x0, x1 = cx - half_px / TILE_PX, cx + half_px / TILE_PX
    y0, y1 = cy - half_px / TILE_PX, cy + half_px / TILE_PX
    tx0, ty0, tx1, ty1 = int(x0), int(y0), int(x1), int(y1)

    rows = []
    for ty in range(ty0, ty1 + 1):
        cols = []
        for tx in range(tx0, tx1 + 1):
            try:
                cols.append(terrain_value(fetch_tile(z, tx, ty)))
            except Exception as e:  # network hiccup on one tile
                print(f"  ! tile {z}/{tx}/{ty}: {e}")
                cols.append(np.zeros((TILE_PX, TILE_PX)))
        rows.append(np.hstack(cols))
    big = np.vstack(rows)

    # pixel-space window of the requested patch
    left = int(round((x0 - tx0) * TILE_PX))
    top = int(round((y0 - ty0) * TILE_PX))
    size = int(round(2 * half_px))
    win = big[top:top + size, left:left + size]
    return win, size * m


def write_png(gray, path, dither=1.0):
    """8-bit is all MuJoCo keeps, so dither the quantization to avoid contour banding."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    rng = np.random.default_rng(0)
    noisy = gray + rng.uniform(-0.5, 0.5, gray.shape) * dither
    Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8), mode="L").save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--half", type=float, default=100.0, help="half width in metres")
    ap.add_argument("--zoom", type=int, default=0, help="0 = auto from patch size")
    ap.add_argument("--maxzoom", type=int, default=15, help="Terrarium tops out at 15")
    ap.add_argument("--px", type=int, default=200, help="output resolution (px)")
    ap.add_argument("--out", default="dem.png")
    ap.add_argument("--name", default="")
    args = ap.parse_args()

    z = args.zoom
    if z == 0:
        # pick the zoom whose native resolution is >= requested px per patch
        need = (2 * args.half) / args.px
        z = max(2, min(17, int(round(math.log2(156543.03392 * math.cos(math.radians(args.lat)) / need)))))
    z = min(z, args.maxzoom)
    native_px = (2 * args.half) / mpp(args.lat, z)
    print(f"scene: {2 * args.half:.0f} m square @ lat {args.lat}, lon {args.lon}")
    print(f"zoom z={z}, native {mpp(args.lat, z):.2f} m/px -> {native_px:.0f} px native")
    if args.px > native_px * 1.5:
        print(f"  note: upsampling {native_px:.0f} -> {args.px} px (no extra detail; "
              f"~{2 * args.half / max(native_px, 1):.1f} m true resolution)")

    h, extent = sample(z, args.half, args.lat, args.lon)
    h = np.where(h < -1000.0, np.nan, h)  # Terrarium no-data guard
    if np.isnan(h).any():
        h = np.nan_to_num(h, nan=float(np.nanmin(h)))
    if h.shape[0] != args.px:
        img = Image.fromarray(h.astype(np.float32), mode="F")
        h = np.asarray(img.resize((args.px, args.px), Image.BICUBIC), dtype=np.float64)

    lo, hi = float(h.min()), float(h.max())
    print(f"elevation range: {lo:.1f} .. {hi:.1f} m  (relief {hi - lo:.1f} m)")
    print(f"mean slope estimate: {np.abs(np.diff(h, axis=0)).mean():.2f} m/px")

    # MuJoCo hfield PNG row 0 = +Y (north); the stitched tile array is already north-up.
    gray = np.clip((h - lo) / max(hi - lo, 1e-6) * 255.0, 0, 255)
    write_png(gray, args.out)

    meta = f"{args.out}.txt"
    with open(meta, "w", encoding="utf-8") as f:
        f.write(f"lat={args.lat}\nlon={args.lon}\nzoom={z}\nextent_m={extent:.1f}\n")
        f.write(f"elev_min={lo:.2f}\nelev_max={hi:.2f}\nrelief={hi - lo:.2f}\npx={args.px}\n")
    print(f"wrote {args.out} ({args.px}x{args.px}) and {meta}")
    print(f'MJCF hint: <hfield name="terrain" file="{os.path.basename(args.out)}" '
          f'size="{extent / 2:.1f} {extent / 2:.1f} {hi - lo:.2f} 0.0"/>')


if __name__ == "__main__":
    main()
