r"""G1 坡面测试：逐点站立 / 行走，对比观测重力的两种口径。

    python test_g1_slope.py --vx 0.5 --seconds 10                 # 默认几个坡度的点
    python test_g1_slope.py --vx 0 --seconds 4 --frames world,road
    python test_g1_slope.py --at 3.6 -22 --frames road --seconds 20

`world` = 官方口径（真实重力方向）；`road` = 把重力旋到路面坐标系（坡面上"以为在平地"）。
"""
import argparse
import os

import mujoco
import numpy as np

import terrain_road
from g1_walker import G1Walker, DEFAULT

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_XML = os.path.join(HERE, "..", "g1_village_final.xml")
# 平地基准 + 修路后主路/支路上的几个坡度点（坡度由地形决定，见 _tmp_slope_census.py）
DEFAULT_POINTS = [
    (-4.0, -62.0),   # 主路尽头，平地
    (3.6, -22.0),    # 主路，约 8°
    (1.0, -20.0),    # 约 8°
    (6.0, 2.0),      # 约 8°
]


def ground_z(m, d, x, y):
    hf = int(m.geom_dataid[int(np.flatnonzero(
        m.geom_type == mujoco.mjtGeom.mjGEOM_HFIELD)[0])])
    gid = np.zeros(1, dtype=np.int32)
    for dx, dy in [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2), (5, 0), (0, 5)]:
        dist = mujoco.mj_ray(m, d, np.array([x + dx, y + dy, 300.0]),
                             np.array([0.0, 0.0, -1.0]), None, 1, -1, gid)
        if dist > 0 and int(gid[0]) == hf:
            return 300.0 - dist
    return 0.8


def run(xml, x, y, vx, seconds, frame, npz=None):
    m = terrain_road.load_model(xml, path=npz or terrain_road.NPZ)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)          # 必须先算几何位姿，否则 mj_ray 拿到的是零位几何
    d.qpos[0:3] = [x, y, ground_z(m, d, x, y) + 0.78]
    d.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    d.qpos[7:19] = DEFAULT
    mujoco.mj_forward(m, d)

    w = G1Walker(m, d, gravity_frame=frame)
    start = np.array([d.qpos[0], d.qpos[1]])
    up0 = w.up()
    fell_at, zs = None, []
    for k in range(int(seconds / 0.02)):
        w.step(vx, 0.0)
        zs.append(float(d.qpos[2]))
        if w.up() < 0.2:
            fell_at = (k + 1) * 0.02
            break
    pos = w.pos()
    slope = float(np.degrees(np.arccos(np.clip(
        terrain_road.plane_normal(m, d, x, y)[2], -1.0, 1.0))))
    return dict(
        x=x, y=y, frame=frame, slope=slope,
        t=(len(zs) * 0.02), dist=float(np.linalg.norm(pos - start)),
        speed=float(np.linalg.norm(pos - start) / max(1e-9, len(zs) * 0.02)),
        z0=float(d.qpos[2]) if not zs else zs[0], zmin=min(zs) if zs else float("nan"),
        up0=up0, up=w.up(), fell=fell_at,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=DEFAULT_XML)
    ap.add_argument("--npz", default="")
    ap.add_argument("--at", nargs=2, type=float, default=None)
    ap.add_argument("--vx", type=float, default=0.5)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--frames", default="world,road")
    a = ap.parse_args()

    pts = [tuple(a.at)] if a.at else DEFAULT_POINTS
    frames = [f.strip() for f in a.frames.split(",") if f.strip()]
    print("%-16s %-6s %6s %6s %7s %7s %7s %8s"
          % ("point(x,y)", "frame", "slope", "t(s)", "dist", "speed", "up", "fell@"))
    for x, y in pts:
        for fr in frames:
            r = run(a.xml, x, y, a.vx, a.seconds, fr, a.npz or None)
            print("%-16s %-6s %6.1f %6.2f %7.2f %7.2f %7.3f %8s"
                  % ("(%.1f,%.1f)" % (r["x"], r["y"]), fr, r["slope"], r["t"],
                     r["dist"], r["speed"], r["up"],
                     "%.2f" % r["fell"] if r["fell"] else "-"))


if __name__ == "__main__":
    main()
