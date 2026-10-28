"""给物理孪生场景加“粗碰撞代理”：把展示场景里的建筑碰撞体 / 大石头搬成静态几何，
这样机器人在孪生里会被真的挡住，镜像到展示场景就不会穿墙。

    python make_twin_proxies.py            # 生成 ../village_walk_props.xml
"""
import os
import re

import mujoco
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(BASE, "..", "demo_v32.xml")
TWIN = os.path.join(BASE, "..", "village_walk4_patch.xml")
OUT = os.path.join(BASE, "..", "village_walk_props.xml")


def quat_rot(q):
    w, x, y, z = q
    return np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - w*z), 2*(x*z + w*y)],
        [2*(x*y + w*z), 1 - 2*(x*x + z*z), 2*(y*z - w*x)],
        [2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y)],
    ])


def main():
    m = mujoco.MjModel.from_xml_path(DEMO)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) or "" for i in range(m.nbody)]

    geoms = []
    # 1) 建筑碰撞体（body 名以 _collision 结尾 / 含 collision）
    for g in range(m.ngeom):
        bn = names[int(m.geom_bodyid[g])]
        if "collision" not in bn.lower():
            continue
        if m.geom_type[g] not in (mujoco.mjtGeom.mjGEOM_BOX, mujoco.mjtGeom.mjGEOM_CYLINDER):
            continue
        b = int(m.geom_bodyid[g])
        pos = d.xpos[b] + quat_rot(d.xquat[b]) @ m.geom_pos[g]
        quat = d.xquat[b]  # 只处理 box/cylinder 近似轴对齐的情形
        geoms.append(("box", pos, quat, m.geom_size[g].copy(), bn))

    # 2) 大石头 / 瓦砾锥（半径 > 0.9 且在行走区域附近）
    cnt_rock = 0
    for g in range(m.ngeom):
        bn = names[int(m.geom_bodyid[g])]
        low = bn.lower()
        if not any(k in low for k in ("rock", "boulder", "debris_cone", "slab")):
            continue
        r = float(m.geom_rbound[g])
        if r < 1.2:
            continue
        p = d.geom_xpos[g]
        if not (-45 <= p[0] <= 45 and -45 <= p[1] <= 45):
            continue
        geoms.append(("sphere", np.array(p), np.array([1.0, 0, 0, 0]), np.array([r * 0.85]), bn))
        cnt_rock += 1

    parts = []
    for i, (kind, pos, quat, size, bn) in enumerate(geoms):
        if kind == "box":
            parts.append(
                '    <geom name="proxy_%d" type="box" pos="%.3f %.3f %.3f" quat="%.5f %.5f %.5f %.5f" '
                'size="%.3f %.3f %.3f" rgba="0 0 0 0" contype="1" conaffinity="1" friction="0.9 0.01 0.001"/>'
                % (i, pos[0], pos[1], pos[2], quat[0], quat[1], quat[2], quat[3],
                   size[0], size[1], size[2]))
        else:
            parts.append(
                '    <geom name="proxy_%d" type="sphere" pos="%.3f %.3f %.3f" size="%.3f" '
                'rgba="0 0 0 0" contype="1" conaffinity="1" friction="0.9 0.01 0.001"/>'
                % (i, pos[0], pos[1], pos[2], size[0]))

    s = open(TWIN, encoding="utf-8").read()
    block = "\n".join(parts)
    assert "</worldbody>" in s
    s = s.replace("</worldbody>", block + "\n  </worldbody>", 1)
    open(OUT, "w", encoding="utf-8").write(s)
    print("生成 %s：建筑碰撞体 + 石头 共 %d 个代理（其中石头 %d）" % (OUT, len(geoms), cnt_rock))


if __name__ == "__main__":
    main()
