r"""在整平区的过渡带边缘撒一圈碎石/砖块，把"房子像摆在一块平台上"的接缝盖掉。

    python seam_ring.py --in ..\\demo_v23.xml --out ..\\demo_v24.xml

只加碎块（复用已有的 rb_rock / brick 资产），不引入新贴图，面数增量约 10 万。
"""
import argparse
import json
import math
import os
import re

import numpy as np

from polish import ASSETS, terrain_fn

# 房子整平 footprint 之外，过渡带大约 6 m（flatten_sites.py）
# 接缝（坡折）就在 footprint+6 那条线上，碎石要压在它上面才有用
RING_IN, RING_OUT = 5.2, 7.4
PER_PLOT = 42


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ASSETS, "demo_v23.xml"))
    ap.add_argument("--out", dest="dst", default=os.path.join(ASSETS, "demo_v24.xml"))
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--per-plot", type=int, default=PER_PLOT)
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(ASSETS, "buildings.json"), encoding="utf-8"))
    plots = [p for p in cfg["plots"] if (p.get("model") or "").strip()]

    xml = open(args.src, encoding="utf-8").read()
    tz = terrain_fn(args.src)
    rng = np.random.default_rng(args.seed)

    bodies, n_rock, n_box = [], 0, 0
    for p in plots:
        a = math.radians(p["yaw"])
        hw, hd = p["size"][0] / 2, p["size"][1] / 2
        for k in range(args.per_plot):
            ang = 2 * math.pi * k / args.per_plot + rng.normal(0, 0.05)
            extra = rng.uniform(RING_IN, RING_OUT)
            lx = (hw + extra) * math.cos(ang)
            ly = (hd + extra) * math.sin(ang)
            x = p["x"] + lx * math.cos(a) - ly * math.sin(a)
            y = p["y"] + lx * math.sin(a) + ly * math.cos(a)
            z = tz(x, y)
            if z is None:
                continue
            r = rng.random()
            if r < 0.62:                      # 小石头（低模 2.3k 面）
                nm = "rb_rock0" if rng.random() < 0.7 else "rb_rock1"
                geo = (f'<geom type="mesh" mesh="{nm}" material="rb_rock_mat" '
                       f'friction="1.1 0.02 0.001"/>')
                n_rock += 1
            elif r < 0.86:                    # 细碎砖块（12 个面，便宜），压小一点别像箱子
                sx, sy, sz = (rng.uniform(0.10, 0.28) for _ in range(3))
                geo = (f'<geom type="box" size="{sx:.2f} {sy:.2f} {sz:.2f}" '
                       f'pos="0 0 {sz:.2f}" material="brick" friction="1.1 0.02 0.001"/>')
                n_box += 1
            else:
                continue
            bodies.append(
                f'<body name="seam_{p["id"]}_{k}" pos="{x:.2f} {y:.2f} {z - 0.12:.3f}" '
                f'euler="0 0 {rng.uniform(0, 360):.1f}">{geo}</body>')

    xml = xml.replace("</worldbody>", "".join(bodies) + "</worldbody>", 1)
    open(args.dst, "w", encoding="utf-8").write(xml)
    print(f"seam ring: {len(plots)} 栋, {len(bodies)} 块"
          f"（石头 {n_rock} + 砖块 {n_box}）-> {os.path.basename(args.dst)}")


if __name__ == "__main__":
    main()
