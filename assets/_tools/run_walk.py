r"""打开窗口看 Go2 走路（爬行步态，六秒内稳定）。

    python run_walk.py                  # 交互窗口
    python run_walk.py --headless --sim 6
"""
import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)

parser = argparse.ArgumentParser()
parser.add_argument("--xml", default=os.path.join(ASSETS, "yard_flat.xml"))
parser.add_argument("--headless", action="store_true")
parser.add_argument("--sim", type=float, default=0.0, help="先跑这么多秒再开窗口")
args = parser.parse_args()

import mujoco  # noqa: E402

sys.path.insert(0, os.path.join(ASSETS, "_tools"))
from walk_go2 import CRAWL_PHASE, LEGS, make_controller  # noqa: E402

m = mujoco.MjModel.from_xml_path(args.xml)
d = mujoco.MjData(m)
if m.nkey > 0:
    mujoco.mj_resetDataKeyframe(m, d, 0)
mujoco.mj_forward(m, d)

ctrl = make_controller(m, freq=2.0, a_thigh=0.22, a_calf=0.55, thigh0=0.95,
                       gait="crawl")
bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
print(f"Go2 爬行步态：freq 2.0 Hz  目标速度 ≈0.43 m/s")

if args.headless or args.sim > 0:
    n = int((args.sim or 6.0) / m.opt.timestep)
    for i in range(n):
        ctrl(m, d, i * m.opt.timestep)
        mujoco.mj_step(m, d)
    print(f"跑了 {n * m.opt.timestep:.1f} s | 位移 {math.hypot(d.xpos[bid][0], d.xpos[bid][1]):.2f} m "
          f"| 机身 z {d.xpos[bid][2]:.2f}")
    if args.headless:
        raise SystemExit(0)

import mujoco.viewer  # noqa: E402

i = 0
with mujoco.viewer.launch_passive(m, d) as v:
    v.cam.lookat[:] = [0.0, 0.0, 0.3]
    v.cam.distance = 2.5
    while v.is_running():
        ctrl(m, d, i * m.opt.timestep)
        mujoco.mj_step(m, d)
        i += 1
        v.cam.lookat[:] = [float(d.xpos[bid][0]), float(d.xpos[bid][1]), 0.25]
        v.sync()
