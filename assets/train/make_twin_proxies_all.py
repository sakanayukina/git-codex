"""全量碰撞代理：把 demo_v32 里除地形/机器人外的所有实体 geom（半径 >= 0.2 m）
做成不可见球代理，写进孪生场景，避免机器人穿过瓦砾/木板/石头。

    python make_twin_proxies_all.py [--out ../village_walk_props_all.xml]
"""
import argparse
import os

import mujoco
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(BASE, "..", "demo_v32.xml")
TWIN = os.path.join(BASE, "..", "village_walk4_patch.xml")
DEFAULT_OUT = os.path.join(BASE, "..", "village_walk_props_all.xml")


def robot_bodies(m):
    out = set()
    for key in ("go2_base", "pelvis"):
        b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, key)
        if b < 0:
            continue
        stack = [b]
        while stack:
            x = stack.pop()
            out.add(x)
            stack.extend(j for j in range(m.nbody) if int(m.body_parentid[j]) == x)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--min-r", type=float, default=0.2)
    ap.add_argument("--scale", type=float, default=0.7)
    a = ap.parse_args()

    m = mujoco.MjModel.from_xml_path(DEMO)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)

    hf = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    skip = robot_bodies(m)

    parts = []
    n = 0
    for g in range(m.ngeom):
        if g == hf or int(m.geom_bodyid[g]) in skip:
            continue
        r = float(m.geom_rbound[g])
        if r < a.min_r:
            continue
        p = d.geom_xpos[g]
        if not (-60.0 <= p[0] <= 60.0 and -60.0 <= p[1] <= 60.0):
            continue
        parts.append(
            '    <geom name="prox_%d" type="sphere" pos="%.3f %.3f %.3f" size="%.3f" '
            'rgba="0 0 0 0" contype="1" conaffinity="1" friction="0.9 0.01 0.001"/>'
            % (n, p[0], p[1], p[2], r * a.scale))
        n += 1

    s = open(TWIN, encoding="utf-8").read()
    block = "\n".join(parts)
    s = s.replace("</worldbody>", block + "\n  </worldbody>", 1)
    open(a.out, "w", encoding="utf-8").write(s)
    print("生成 %s：%d 个球代理（min_r=%.2f, scale=%.2f）" % (a.out, n, a.min_r, a.scale))


if __name__ == "__main__":
    main()
