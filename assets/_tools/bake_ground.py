r"""把路直接画进地面贴图（1:1 覆盖整块地形），避免贴地网格的抖动、锯齿和阴影自遮挡。

    from bake_ground import bake
    bake(extent=200, roads=[(main_pts, 3.6), (spur_pts, 2.4)],
         ground_png="tex/leafy_grass_diffuse.png", out_png="tex/ground_baked.png")

产物配合 hfield 材质 texrepeat="1 1" 使用：路是"长在地形上"的，没有浮空。
"""
import argparse
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def world_to_px(x, y, extent, size):
    """hfield 的 PNG 行 0 = +Y，这里保持一致。"""
    return ((x + extent / 2) / extent * size,
            (extent / 2 - y) / extent * size)


def make_noise(size, scale=128, rng=None):
    rng = rng or np.random.default_rng(0)
    small = rng.normal(0.5, 0.12, (scale, scale))
    img = Image.fromarray(np.clip(small * 255, 0, 255).astype(np.uint8), "L")
    return img.resize((size, size), Image.BICUBIC)


def _draw_road(draw, points, width, extent, size, rng):
    pts = [world_to_px(x, y, extent, size) for x, y in points]
    if len(pts) < 2:
        return
    half_w = width / extent * size / 2
    # 路肩（被车压实的浅色边）
    draw.line(pts, fill=(132, 112, 82, 140), width=int(half_w * 2 + size / 200), joint="curve")
    # 路面
    draw.line(pts, fill=(112, 92, 66, 255), width=int(half_w * 2), joint="curve")
    # 两条车辙
    for off in (-0.55, 0.55):
        ruts = []
        for i, (px, py) in enumerate(pts):
            if i + 1 < len(pts):
                dx, dy = pts[i + 1][0] - px, pts[i + 1][1] - py
            else:
                dx, dy = px - pts[i - 1][0], py - pts[i - 1][1]
            L = math.hypot(dx, dy) or 1.0
            ruts.append((px - dy / L * half_w * off, py + dx / L * half_w * off))
        draw.line(ruts, fill=(92, 74, 52, 190), width=max(2, int(half_w * 0.4)), joint="curve")


def bake(extent, roads, ground_png, out_png, size=2048, tile_m=200.0, seed=7):
    ground = Image.open(ground_png).convert("RGB")
    # 草贴图偏黄：压红、提绿、压蓝，让它像林地而不是沙地
    r, g, b = ground.split()
    ground = Image.merge("RGB", [
        r.point(lambda v: int(v * 0.82)),
        g.point(lambda v: min(255, int(v * 1.04))),
        b.point(lambda v: int(v * 0.70)),
    ])

    canvas = Image.new("RGB", (size, size))
    step = int(tile_m / extent * size) or size
    for gy in range(0, size, step):
        for gx in range(0, size, step):
            canvas.paste(ground.resize((step, step), Image.LANCZOS), (gx, gy))

    draw = ImageDraw.Draw(canvas, "RGBA")
    rng = np.random.default_rng(seed)
    for points, width in roads:
        _draw_road(draw, points, width, extent, size, rng)

    # 路面上撒一点草色斑块，像少有人走的斑驳
    patch = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gp = ImageDraw.Draw(patch)
    for points, width in roads:
        pts = [world_to_px(x, y, extent, size) for x, y in points]
        half_w = width / extent * size / 2
        for _ in range(int(size * size / 12000)):
            t = rng.integers(0, max(1, len(pts) - 1))
            (x0, y0) = pts[t]
            (x1, y1) = pts[min(t + 1, len(pts) - 1)]
            a = rng.uniform(0, 1)
            cx, cy = x0 + (x1 - x0) * a, y0 + (y1 - y0) * a
            off = rng.uniform(-half_w, half_w)
            L = math.hypot(x1 - x0, y1 - y0) or 1.0
            cx += -(y1 - y0) / L * off
            cy += (x1 - x0) / L * off
            rad = rng.uniform(1.2, 4.5)
            gp.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
                       fill=(96, 120, 62, int(rng.uniform(40, 130))))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), patch).convert("RGB")

    # 全图亮度噪声，压掉平涂感
    canvas = Image.blend(canvas, make_noise(size, 128, rng).convert("RGB"), 0.06)

    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    canvas.save(out_png, optimize=True)
    return out_png, canvas.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(ASSETS, "buildings.json"))
    ap.add_argument("--ground", default=os.path.join(ASSETS, "tex", "leafy_grass_diffuse.png"))
    ap.add_argument("--out", default=os.path.join(ASSETS, "tex", "ground_baked.png"))
    ap.add_argument("--extent", type=float, default=200.0)
    ap.add_argument("--size", type=int, default=2048)
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    roads = [(cfg["road"]["points"], cfg["road"]["width"])]
    out, sz = bake(args.extent, roads, args.ground, args.out, args.size)
    print(f"wrote {os.path.relpath(out, ASSETS)} {sz[0]}x{sz[1]} "
          f"({os.path.getsize(out)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
