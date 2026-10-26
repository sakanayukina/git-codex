r"""在 hfield 上局部压平一小块地（给机器人一条可走的短走廊）。

    python flatten_patch.py --xml ../demo_v31.xml --out ../demo_v32.xml \
        --cx 12.0 --cy -19.0 --rx 4.0 --ry 3.0 --feather 1.5

原理：把目标矩形内的高度改成该区域中位数高度，边缘用 smoothstep 过渡，
其余地形一律不动。只重写 hfield 的 PNG，并让新场景引用它。

为什么需要：村里 DEM 是 8 位量化（每级 0.26 m），机器人策略抬腿只有 2–3 cm，
必须给它一段平整可走的地面，否则一迈步就摔。
"""
import argparse
import os
import re
import shutil

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=os.path.join(ASSETS, "demo_v31.xml"))
    ap.add_argument("--out", default=os.path.join(ASSETS, "demo_v32.xml"))
    ap.add_argument("--cx", type=float, default=12.0)
    ap.add_argument("--cy", type=float, default=-19.0)
    ap.add_argument("--rx", type=float, default=4.0)
    ap.add_argument("--ry", type=float, default=3.0)
    ap.add_argument("--feather", type=float, default=1.5)
    a = ap.parse_args()

    xml = open(a.xml, encoding="utf-8").read()

    # 找 hfield 定义（属性可能跨行）
    hm = re.search(r"<hfield\b[^>]*>", xml, re.S)
    if not hm:
        raise SystemExit("找不到 hfield")
    tag = hm.group(0)
    name = re.search(r'name="([^"]+)"', tag).group(1)
    png_rel = re.search(r'file="([^"]+)"', tag).group(1)
    size_str = re.search(r'size="([^"]+)"', tag).group(1)
    sx, sy, ztop, base = (float(v) for v in size_str.split())
    gm = re.search(r'<geom[^>]*hfield="%s"[^>]*pos="([^"]+)"' % re.escape(name), xml)
    pos = [float(v) for v in gm.group(1).split()] if gm else [0.0, 0.0, 0.0]
    print(f"hfield: size={sx} {sy} {ztop} {base}  pos={pos}  file={png_rel}")

    src_png = os.path.join(ASSETS, png_rel)
    img = Image.open(src_png).convert("L")
    arr = np.asarray(img, dtype=np.float64)
    H, W = arr.shape
    print(f"高度图 {W}x{H}")

    # 世界坐标 -> 像素（与 polish.terrain_fn 一致：row 随 +y 增长）
    def to_px(x, y):
        u = (x - pos[0]) / (2 * sx) + 0.5
        v = (y - pos[1]) / (2 * sy) + 0.5
        return u * (W - 1), v * (H - 1)

    # 采样区域中位数作为目标高度（用双线性，粗略即可）
    ys = np.linspace(a.cy - a.ry, a.cy + a.ry, 25)
    xs = np.linspace(a.cx - a.rx, a.cx + a.rx, 33)
    vals = []
    for y in ys:
        for x in xs:
            u, v = to_px(x, y)
            vals.append(arr[int(round(v)), int(round(u))])
    target = float(np.median(vals))
    print(f"目标高度（灰度）= {target:.1f}")

    # 逐像素重写：区域内置为目标值，外围 feather 宽度 smoothstep 过渡
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    wx = (uu / (W - 1)) * (2 * sx) + pos[0] - sx
    wy = (vv / (H - 1)) * (2 * sy) + pos[1] - sy
    dx = np.abs(wx - a.cx) - a.rx
    dy = np.abs(wy - a.cy) - a.ry
    d = np.maximum(dx, dy)                     # <=0 在矩形内
    t = np.clip(1.0 - d / a.feather, 0.0, 1.0)
    w = t * t * (3 - 2 * t)                    # smoothstep
    new = arr * (1 - w) + target * w
    # 量化回 8 位；区域内强制同一个值，保证绝对平整
    new = np.where(d <= 0, target, new)
    out = np.clip(np.round(new), 0, 255).astype(np.uint8)

    changed = int(np.sum(np.abs(out.astype(int) - arr.astype(int)) > 0))
    print(f"改写像素 {changed} 个（{changed / (W * H) * 100:.1f}%）")

    out_rel = os.path.join(os.path.dirname(png_rel), "height_field_patch.png").replace("\\", "/")
    Image.fromarray(out).save(os.path.join(ASSETS, out_rel))
    new_tag = tag.replace(png_rel, out_rel)
    xml2 = xml.replace(tag, new_tag, 1)
    open(a.out, "w", encoding="utf-8").write(xml2)
    print(f"wrote {os.path.relpath(a.out, ASSETS)}（hfield → {out_rel}）")


if __name__ == "__main__":
    main()
