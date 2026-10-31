"""最终版碰撞代理：建筑盒 + 石头（贴合）+ 其它道具。

- 建筑：所有 `*_collision` body 的 box/cylinder 原样搬进来
- 石头：body 名含 rock/boulder/slab/stone/stump/debris_cone → 半径 0.9 × rbound 的球
- 其它道具（木板/箱体/轮胎等）：半径 0.5 × rbound 的球，仅 r ≥ 0.35

    python make_twin_proxies_final.py
    python make_twin_proxies_final.py --base ../g1_terrain_plain.xml \
        --out ../g1_village_final.xml
"""
import argparse
import os
import re

import mujoco
import numpy as np

from roadmask import RoadMask

BASE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(BASE, "..", "demo_v32.xml")
TWIN = os.path.join(BASE, "..", "village_walk4_patch.xml")
DEFAULT_OUT = os.path.join(BASE, "..", "village_walk_final.xml")

ROCK_KEYS = ("rock", "boulder", "debris_cone", "slab", "stone", "stump")


def quat_rot(q):
    w, x, y, z = q
    return np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - w*z), 2*(x*z + w*y)],
        [2*(x*y + w*z), 1 - 2*(x*x + z*z), 2*(y*z - w*x)],
        [2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y)],
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", default=DEMO)
    ap.add_argument("--base", default=TWIN,
                    help="被追加代理的轻量物理场景")
    ap.add_argument("--hfield",
                    help="覆盖 base 场景的 hfield 文件路径（相对 XML 所在目录）")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--rock-scale", type=float, default=0.9)
    ap.add_argument("--seam-min-r", type=float, default=0.15,
                    help="接缝小石头的碰撞代理最小半径")
    ap.add_argument("--prop-scale", type=float, default=0.5)
    ap.add_argument("--prop-min-r", type=float, default=0.35)
    ap.add_argument("--clear-road", action="store_true",
                    help="把压在路面上的物体从物理层里删掉（默认关闭："
                         "物理必须与展示一致，否则镜像机器人会穿过石头）")
    a = ap.parse_args()

    import terrain_road
    m = terrain_road.load_model(a.demo)   # 注入 float 地形，代理 z 与物理场景一致
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) or "" for i in range(m.nbody)]

    robot = set()
    for key in ("go2_base", "pelvis"):
        b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, key)
        if b >= 0:
            stack = [b]
            while stack:
                x = stack.pop()
                robot.add(x)
                stack.extend(j for j in range(m.nbody) if int(m.body_parentid[j]) == x)

    parts, n_box, n_rock, n_small, n_prop = [], 0, 0, 0, 0
    rm = RoadMask()          # 修路后：路面上不放碰撞代理（否则石头会横在路中间）
    n_cleared = 0
    for g in range(m.ngeom):
        bid = int(m.geom_bodyid[g])
        bn = names[bid]
        low = bn.lower()
        p = d.geom_xpos[g]

        # 1) 建筑碰撞体
        if "collision" in low and m.geom_type[g] in (
                mujoco.mjtGeom.mjGEOM_BOX, mujoco.mjtGeom.mjGEOM_CYLINDER):
            sz = m.geom_size[g]
            parts.append(
                '    <geom name="bld_%d" type="box" pos="%.3f %.3f %.3f" size="%.3f %.3f %.3f" '
                'rgba="0 0 0 0" contype="1" conaffinity="1" friction="0.9 0.01 0.001"/>'
                % (n_box, p[0], p[1], p[2], sz[0], sz[1], sz[2]))
            n_box += 1
            continue

        if bid in robot or m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD:
            continue
        if not (-55.0 <= p[0] <= 55.0 and -55.0 <= p[1] <= 55.0):
            continue

        r = float(m.geom_rbound[g])

        # 路面上（含路肩 0.15 m）的石头/道具默认**照样放代理**：
        # 展示层里它们看得见，物理层就必须挡得住，否则镜像机器人会穿过去。
        # 路线绕行交给 A*（nav_grid.py）解决，不靠"把障碍删掉"。
        if a.clear_road and rm.intrudes(p[0], p[1], r * a.rock_scale + 0.15):
            n_cleared += 1
            continue

        # 2) 石头（贴合一点）
        is_rock = any(k in low for k in ROCK_KEYS) and r >= 0.4
        is_seam_stone = low.startswith("seam_") and r >= a.seam_min_r
        if is_rock or is_seam_stone:
            parts.append(
                '    <geom name="rk_%d" type="sphere" pos="%.3f %.3f %.3f" size="%.3f" '
                'rgba="0 0 0 0" contype="1" conaffinity="1" friction="0.9 0.01 0.001"/>'
                % (n_rock, p[0], p[1], p[2], r * a.rock_scale))
            n_rock += 1
            n_small += int(is_seam_stone and not is_rock)
            continue

        # 3) 其它道具
        if r >= a.prop_min_r:
            parts.append(
                '    <geom name="pr_%d" type="sphere" pos="%.3f %.3f %.3f" size="%.3f" '
                'rgba="0 0 0 0" contype="1" conaffinity="1" friction="0.9 0.01 0.001"/>'
                % (n_prop, p[0], p[1], p[2], r * a.prop_scale))
            n_prop += 1

    s = open(a.base, encoding="utf-8").read()
    if a.hfield:
        s, count = re.subn(
            r'(<hfield\b[^>]*\bfile=")[^"]+(")',
            lambda m: m.group(1) + a.hfield + m.group(2),
            s, count=1)
        if count != 1:
            raise SystemExit("找不到可替换的 hfield 文件路径")
    s = s.replace("</worldbody>", "\n".join(parts) + "\n  </worldbody>", 1)
    open(a.out, "w", encoding="utf-8").write(s)
    print("生成 %s：建筑 %d / 石头 %d（其中接缝小石头 %d）/ 其它道具 %d / 让路清掉 %d"
          % (a.out, n_box, n_rock, n_small, n_prop, n_cleared), flush=True)


if __name__ == "__main__":
    main()
