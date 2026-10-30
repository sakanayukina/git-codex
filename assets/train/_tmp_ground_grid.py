r"""打印某点周围的地面高度网格（用 mj_ray，和机器人出生用的是同一套查询）。"""
import argparse
import os

import mujoco
import numpy as np

import terrain_road

HERE = os.path.dirname(os.path.abspath(__file__))


def height_at(m, d, x, y, gid, grp, hf):
    dist = mujoco.mj_ray(m, d, np.array([x, y, 300.0]), np.array([0.0, 0.0, -1.0]),
                         grp, 1, -1, gid)
    if dist > 0 and int(gid[0]) == hf:
        return 300.0 - dist
    return float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=os.path.join(HERE, "..", "village_walk_final.xml"))
    ap.add_argument("--at", nargs=2, type=float, default=[3.6, -22.0])
    ap.add_argument("--extent", type=float, default=0.6)
    ap.add_argument("--step", type=float, default=0.1)
    a = ap.parse_args()

    m = terrain_road.load_model(a.xml)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    hf = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    gid = np.array([-1], dtype=np.int32)
    grp = np.ones(6, dtype=np.uint8)

    x0, y0 = a.at
    xs = np.arange(-a.extent, a.extent + 1e-9, a.step)
    print("高度网格 Δz（相对中心），单位 mm；行 = y 从 %.1f 到 %.1f"
          % (y0 - a.extent, y0 + a.extent))
    z0 = height_at(m, d, x0, y0, gid, grp, hf)
    for dy in xs[::-1]:
        row = [height_at(m, d, x0 + dx, y0 + dy, gid, grp, hf) - z0 for dx in xs]
        print("y%+.1f " % dy + " ".join("%5.0f" % (v * 1000) for v in row))
    print("中心高度 %.4f m" % z0)
    vals = [height_at(m, d, x0 + dx, y0 + dy, gid, grp, hf)
            for dx in np.arange(-0.3, 0.31, 0.1) for dy in np.arange(-0.3, 0.31, 0.1)]
    vals = np.array(vals) - z0
    print("脚掌范围 ±0.3 m：max Δz %.3f m，RMS %.3f m" % (np.nanmax(np.abs(vals)), np.sqrt(np.nanmean(vals ** 2))))


if __name__ == "__main__":
    main()
