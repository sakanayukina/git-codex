r"""把 float DEM 做成一版三角网地形（**仅训练/实验分支**，不改展示场景）。

    python make_terrain_trimesh.py --half 40 --res 2.0

产物：
    train/_terrain/dem_patch.obj    三角网（float 精度，坡面连续）
    train/_terrain/dem_patch.xml    可直接被场景 include 的地形片段
    train/_terrain/dem_patch_meta.json

为什么单独做：展示场景 demo_v29 保留 hfield（8 位，0.26 m 台阶但已经稳定）；
训练分支需要连续坡面，用 trimesh 才能提供真实坡度而不引入量化台阶。
"""
import argparse
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
NPZ = os.path.join(ASSETS, "terrain", "dem_float.npz")
OUT = os.path.join(ASSETS, "train", "_terrain")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", type=float, default=40.0, help="patch 半宽（米）")
    ap.add_argument("--res", type=float, default=2.0, help="网格间距（米）")
    a = ap.parse_args()

    d = np.load(NPZ)
    z = d["z"].astype(np.float64)
    extent = float(d["extent"])
    H, W = z.shape
    cell = extent / W
    # 世界坐标：行 0 = +Y（与 polish.terrain_fn 一致）
    xs = (np.arange(W) + 0.5) * cell - extent / 2
    ys = extent / 2 - (np.arange(H) + 0.5) * cell

    # 取中心附近 patch 并重采样到 res 间距
    n = int(2 * a.half / a.res) + 1
    gx = np.linspace(-a.half, a.half, n)
    gy = np.linspace(a.half, -a.half, n)          # 从 +y 到 -y，保持右手系
    GX, GY = np.meshgrid(gx, gy)
    idx_x = np.interp(GX.ravel(), xs, np.arange(W))
    idx_y = np.interp(GY.ravel(), ys[::-1], np.arange(H))
    zi = z[np.clip(idx_y.round().astype(int), 0, H - 1),
           np.clip(idx_x.round().astype(int), 0, W - 1)].reshape(n, n)
    zi -= zi.mean()

    os.makedirs(OUT, exist_ok=True)
    obj = os.path.join(OUT, "dem_patch.obj")
    with open(obj, "w", encoding="utf-8") as f:
        for j in range(n):
            for i in range(n):
                f.write("v %.4f %.4f %.4f\n" % (gx[i], gy[j], zi[j, i]))
        for j in range(n - 1):
            for i in range(n - 1):
                a0 = j * n + i + 1
                f.write("f %d %d %d\n" % (a0, a0 + 1, a0 + n))
                f.write("f %d %d %d\n" % (a0 + 1, a0 + n + 1, a0 + n))

    xml = os.path.join(OUT, "dem_patch.xml")
    with open(xml, "w", encoding="utf-8") as f:
        f.write("""<mujoco>
  <asset>
    <mesh name="dem_patch" file="%s" inertia="shell"/>
  </asset>
  <worldbody>
    <geom name="ground" type="mesh" mesh="dem_patch" friction="1.0 0.02 0.001"/>
  </worldbody>
</mujoco>
""" % obj.replace("\\", "/"))

    gy30, gx30 = np.gradient(zi, a.res)
    slope = np.degrees(np.arctan(np.hypot(gx30, gy30)))
    meta = dict(half=a.half, res=a.res, n=n, tris=2 * (n - 1) ** 2,
                relief=float(zi.max() - zi.min()),
                slope_median=float(np.median(slope)), slope_p95=float(np.percentile(slope, 95)),
                source=str(NPZ))
    json.dump(meta, open(os.path.join(OUT, "dem_patch_meta.json"), "w"), indent=2)

    print("patch %.0f m × %.0f m，%d×%d 顶点，%d 三角面" % (2 * a.half, 2 * a.half, n, n, meta["tris"]))
    print("落差 %.1f m | 坡度 中位 %.1f° / p95 %.1f°" % (meta["relief"], meta["slope_median"], meta["slope_p95"]))
    print("wrote", obj)
    print("wrote", xml)


if __name__ == "__main__":
    main()
