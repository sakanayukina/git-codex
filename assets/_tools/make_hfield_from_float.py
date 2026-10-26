r"""从 float DEM 生成训练用 hfield PNG（真实坡度，不走 8 位回环）。

    python make_hfield_from_float.py --half 40 --px 128 --out train/_terrain/dem80_128.png

输出 8 位 PNG + 打印：像素间距、落差、折算的量化假坡度，便于判断是否可接受。
"""
import argparse
import os

import numpy as np

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_robot_on_trimesh import patch_height
from PIL import Image        # base 环境有 PIL，直接存灰度图


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", type=float, default=40.0)
    ap.add_argument("--px", type=int, default=128)
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "train", "_terrain", "dem80_128.png"))
    a = ap.parse_args()

    gx, gy, zi = patch_height(half=a.half, res=2.0)
    # 双线性重采样到 px×px
    xs = np.linspace(gx[0], gx[-1], a.px)
    ys = np.linspace(gy[0], gy[-1], a.px)
    from numpy import interp
    out = np.zeros((a.px, a.px))
    src_x = np.linspace(gx[0], gx[-1], zi.shape[1])
    for j, y in enumerate(ys):
        row = np.interp(src_x, gx, zi[np.argmin(np.abs(gy - y))])
        out[j] = np.interp(xs, src_x, row)

    out -= out.min()
    relief = float(out.max())
    img = np.clip(out / max(relief, 1e-6) * 255, 0, 255).astype(np.uint8)
    Image.fromarray(img, mode='L').save(a.out)

    cell = 2 * a.half / a.px
    quant = relief / 255.0
    print("输出 %s：%d×%d，覆盖 %.0f m，像素 %.2f m" % (a.out, a.px, a.px, 2 * a.half, cell))
    print("落差 %.1f m（hfield size z 要填这个值）" % relief)
    print("量化：%.3f m/级 → 折算假坡度 %.1f°（真实坡坡中位 9.5°）" % (quant, np.degrees(np.arctan(quant / cell))))
    print("hfield_size=%.0f  relief=%.2f" % (a.half, relief))


if __name__ == "__main__":
    main()
