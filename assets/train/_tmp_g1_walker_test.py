r"""G1Walker 冒烟测试：站着 / 走直线，看是否与 g1_policy.py 的参考结果一致。

    python _tmp_g1_walker_test.py --vx 0 --seconds 4
    python _tmp_g1_walker_test.py --vx 0.5 --seconds 6
"""
import argparse
import os

import mujoco
import numpy as np

import terrain_road
from _tmp_g1_walker_dump import G1Walker, DEFAULT

HERE = os.path.dirname(os.path.abspath(__file__))
XML = os.path.join(HERE, "..", "g1_village_final.xml")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=XML)
    ap.add_argument("--at", nargs=2, type=float, default=[3.6, -22.0])
    ap.add_argument("--vx", type=float, default=0.0)
    ap.add_argument("--vyaw", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=4.0)
    ap.add_argument("--no-inject", action="store_true")
    ap.add_argument("--npz", default="")
    a = ap.parse_args()

    m = terrain_road.load_model(a.xml, inject=not a.no_inject, path=(a.npz or terrain_road.NPZ))
    d = mujoco.MjData(m)
    gx, gy = a.at
    gid = np.array([-1], dtype=np.int32)
    grp = np.ones(6, dtype=np.uint8)
    hf = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    d.qpos[0:3] = [gx + 500.0, gy + 500.0, -800.0]
    mujoco.mj_forward(m, d)
    gz = None
    for dx, dy in [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2)]:
        dist = mujoco.mj_ray(m, d, np.array([gx + dx, gy + dy, 300.0]),
                             np.array([0.0, 0.0, -1.0]), grp, 1, -1, gid)
        if dist > 0 and int(gid[0]) == hf:
            gz = 300.0 - dist
            break
    gz = 0.8 if gz is None else gz
    d.qpos[0:3] = [gx, gy, gz + 0.78]
    d.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    d.qpos[7:19] = DEFAULT
    mujoco.mj_forward(m, d)
    start = np.array([d.qpos[0], d.qpos[1]])
    print("出生 z = %.4f" % d.qpos[2])

    w = G1Walker(m, d)
    n = int(a.seconds / 0.02)
    zs, ups = [], []
    for k in range(n):
        w.step(a.vx, a.vyaw)
        zs.append(float(d.qpos[2]))
        ups.append(w.up())
        if w.up() < 0.2:
            print("摔了 @ %.2f s" % (k * 0.02))
            break
    pos = w.pos()
    print("vx %.2f 跑 %.1f s | 位移 %.2f m | 净位移 %.2f m | z %.3f~%.3f | up 末 %.3f | yaw %.2f"
          % (a.vx, len(zs) * 0.02, float(np.linalg.norm(pos - start)),
             float(np.linalg.norm(pos - start)), min(zs), max(zs), ups[-1], w.yaw()))


if __name__ == "__main__":
    main()
