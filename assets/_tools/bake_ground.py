r"""把路直接画进地面贴图（1:1 覆盖整块地形），避免贴地网格的抖动、锯齿和阴影自遮挡。

v2 改动：
- 路用多边形铺（逐点宽度抖动 ±15% + 横向抖动），边缘不再是一条直尺线
- 车辙更深更宽；路面整体压暗
- 岔口处画一块加宽的"路口补丁"
- 草沿路边侵入，形成不规则路缘

    from bake_ground import bake
    bake(extent=200, roads=[(pts, 4.2), (spur, 3.0)],
         junctions=[(x, y)], ground_png=..., out_png=...)
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
    small = rng.normal(0.5, 0.1, (scale, scale))
    img = Image.fromarray(np.clip(small * 255, 0, 255).astype(np.uint8), "L")
    return img.resize((size, size), Image.BICUBIC)


def _sample_polyline(points, step_px, extent, size):
    """把世界坐标折线按像素步长重采样，返回 [(px, py), ...]。"""
    pts = [world_to_px(x, y, extent, size) for x, y in points]
    out = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L / step_px))
        for i in range(1, n + 1):
            t = i / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def _road_polygon(pts, half_w, rng):
    """沿中线生成左右边，宽度和横向位置都带抖动 → 不规则路缘。"""
    left, right = [], []
    phase = rng.uniform(0, 6.28)
    for i, (px, py) in enumerate(pts):
        if i + 1 < len(pts):
            dx, dy = pts[i + 1][0] - px, pts[i + 1][1] - py
        else:
            dx, dy = px - pts[i - 1][0], py - pts[i - 1][1]
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        s = i / max(1, len(pts) - 1)
        wob = 1.0 + 0.15 * math.sin(s * 21 + phase) + 0.08 * math.sin(s * 57 + phase * 2)
        lateral = rng.normal(0, half_w * 0.06)
        w = half_w * wob
        left.append((px + nx * w + nx * lateral, py + ny * w + ny * lateral))
        right.append((px - nx * w + nx * lateral, py - ny * w + ny * lateral))
    return left + right[::-1]


def _draw_road(draw, points, width, extent, size, rng):
    pts = _sample_polyline(points, step_px=max(2.0, size / extent * 0.5), extent=extent, size=size)
    if len(pts) < 2:
        return
    half_w = width / extent * size / 2
    # 路肩：比路面略宽一圈的浅色（被压实的土）
    draw.polygon(_road_polygon(pts, half_w * 1.18, rng), fill=(126, 106, 76, 130))
    # 路面
    draw.polygon(_road_polygon(pts, half_w, rng), fill=(96, 80, 58, 255))
    # 两条车辙：更深、更宽
    for off in (-0.5, 0.5):
        rut = []
        for i, (px, py) in enumerate(pts):
            if i + 1 < len(pts):
                dx, dy = pts[i + 1][0] - px, pts[i + 1][1] - py
            else:
                dx, dy = px - pts[i - 1][0], py - pts[i - 1][1]
            L = math.hypot(dx, dy) or 1.0
            jitter = rng.normal(0, half_w * 0.03)
            rut.append((px - dy / L * (half_w * off + jitter),
                        py + dx / L * (half_w * off + jitter)))
        draw.line(rut, fill=(72, 58, 40, 210), width=max(2, int(half_w * 0.5)), joint="curve")


def bake(extent, roads, ground_png, out_png, size=2048, tile_m=200.0, junctions=(),
         seed=7):
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

    # 岔口补丁：路口加宽，看起来像真有人在那儿拐弯
    for (jx, jy), jw in junctions:
        cx, cy = world_to_px(jx, jy, extent, size)
        r = jw / extent * size * 0.62
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(96, 80, 58, 255))
        draw.ellipse([cx - r * 0.8, cy - r * 0.8, cx + r * 0.8, cy + r * 0.8],
                     fill=(88, 73, 52, 255))

    # 草沿路边侵入：在路面附近撒草点，形成不规则路缘
    patch = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gp = ImageDraw.Draw(patch)
    for points, width in roads:
        pts = _sample_polyline(points, 3.0, extent, size)
        half_w = width / extent * size / 2
        for _ in range(int(size * size / 9000)):
            t = rng.integers(0, max(1, len(pts) - 1))
            (x0, y0) = pts[t]
            (x1, y1) = pts[min(t + 1, len(pts) - 1)]
            a = rng.uniform(0, 1)
            cx, cy = x0 + (x1 - x0) * a, y0 + (y1 - y0) * a
            edge = rng.uniform(0.75, 1.25)          # 集中在路缘附近
            L = math.hypot(x1 - x0, y1 - y0) or 1.0
            off = rng.uniform(-1, 1) * half_w * edge
            cx += -(y1 - y0) / L * off
            cy += (x1 - x0) / L * off
            rad = rng.uniform(1.5, 5.0)
            gp.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
                       fill=(92, 116, 60, int(rng.uniform(50, 150))))
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
    main_pts = cfg["road"]["points"]
    roads = [(main_pts, cfg["road"]["width"])]
    junctions = []

    # 入户支路：跟 village.py 同一套算法（门 -> 主路最近点），保证贴图对得上
    def closest(px, py, pts):
        best, bd = None, 1e9
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy or 1e-6
            t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
            cx, cy = x0 + dx * t, y0 + dy * t
            d = math.hypot(px - cx, py - cy)
            if d < bd:
                best, bd = (cx, cy), d
        return best

    for p in cfg.get("plots", []):
        a = math.radians(p["yaw"])
        dx, dy = math.sin(a) * p["size"][1] / 2, -math.cos(a) * p["size"][1] / 2
        door = (p["x"] + dx, p["y"] + dy)
        tgt = closest(door[0], door[1], main_pts)
        if tgt is None or math.hypot(door[0] - tgt[0], door[1] - tgt[1]) < 1.0:
            continue
        mid = ((door[0] + tgt[0]) / 2, (door[1] + tgt[1]) / 2)
        roads.append(([tgt, mid, door], 3.0))
        junctions.append((tgt, 3.0))

    out, sz = bake(args.extent, roads, args.ground, args.out, args.size, junctions=junctions)
    print(f"wrote {os.path.relpath(out, ASSETS)} {sz[0]}x{sz[1]} "
          f"({os.path.getsize(out)/1e6:.1f} MB, {len(roads)} 条路)")


if __name__ == "__main__":
    main()
