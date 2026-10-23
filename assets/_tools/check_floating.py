"""最终验证：瓦砾块是否贴地。用 MuJoCo 射线（排除自身）当参照，不自己解 hfield。"""
import sys

import mujoco
import numpy as np

XML = sys.argv[1] if len(sys.argv) > 1 else "demo_v23.xml"
m = mujoco.MjModel.from_xml_path(XML)
d = mujoco.MjData(m)
mujoco.mj_forward(m, d)

gg = np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8)
rows = []
for i in range(m.nbody):
    n = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i)
    if not n or not (n.startswith("blk_") or n.startswith("debris_cone_")):
        continue
    x, y, z = (float(v) for v in m.body_pos[i])
    gid = np.array([-1], dtype=np.int32)
    dist = mujoco.mj_ray(m, d, np.array([x, y, 400.0]), np.array([0.0, 0.0, -1.0]),
                         gg, 1, i, gid)
    if dist < 0:
        continue
    ground = 400.0 - dist
    rows.append((n, z, ground, z - ground))

print(f"瓦砾块 {len(rows)} 个，body 高 vs 地形高（gap 正=悬空，负=嵌入）")
float_ = [r for r in rows if r[3] > 0.3]
deep = [r for r in rows if r[3] < -0.5]
print(f"  悬空 > 0.3 m：{len(float_)}  嵌入 > 0.5 m：{len(deep)}")
for n, z, g, gap in sorted(float_, key=lambda r: -r[3])[:6]:
    print(f"    {n:<22} gap {gap:+.2f} m (body {z:.2f} vs ground {g:.2f})")
