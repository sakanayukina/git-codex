"""测机器人在坡度阶梯上的能力：跑一遍 bc.pt，报位移 / 爬升 / 倾角。

    python measure_capability.py                  # 默认测 _ladder 下所有 slope_*.xml
    python measure_capability.py --glob "slope_*.xml" --seconds 8
"""
import argparse
import glob
import os
import sys

import mujoco
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ppo import ActorCritic
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity

BASE = os.path.dirname(os.path.abspath(__file__))
JOINTS = ["FL_hip", "FL_thigh", "FL_calf", "FR_hip", "FR_thigh", "FR_calf",
          "RL_hip", "RL_thigh", "RL_calf", "RR_hip", "RR_thigh", "RR_calf"]


def run_one(xml, ckpt, seconds):
    m = mujoco.MjModel.from_xml_path(xml)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)

    bb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
    if bb < 0:
        bb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "trunk")
    bj = next(j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE
              and int(m.jnt_bodyid[j]) == bb)
    bq, bd = int(m.jnt_qposadr[bj]), int(m.jnt_dofadr[bj])
    q, dof, act = [], [], []
    for jn in JOINTS:
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn + "_joint")
        q.append(int(m.jnt_qposadr[j])); dof.append(int(m.jnt_dofadr[j]))
        act.append(next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == j))
    q, dof, act = np.array(q), np.array(dof), np.array(act)

    hf = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    hid = int(m.geom_dataid[hf])
    width = 2.0 * float(m.hfield_size[hid][0])   # 场地边长（x 方向）
    gid = np.array([-1], dtype=np.int32); grp = np.ones(6, dtype=np.uint8)

    def ground(x, y):
        dist = mujoco.mj_ray(m, d, np.array([x, y, 300.0]), np.array([0, 0, -1.0]),
                             grp, 1, -1, gid)
        return 300.0 - dist if (dist > 0 and int(gid[0]) == hf) else None

    # 实测坡度：在坡段内部取两点（避开前 15% 平地）
    xa, xb = -0.20 * width, 0.30 * width
    ga, gb = ground(xa, 0.0), ground(xb, 0.0)
    slope = None if (ga is None or gb is None) else np.degrees(np.arctan2(gb - ga, xb - xa))

    x0, y0 = -0.42 * width, 0.0
    gz = ground(x0, y0)
    if gz is None:
        return None
    d.qpos[bq:bq+3] = [x0, y0, gz + 0.45]
    d.qpos[bq+3:bq+7] = [1, 0, 0, 0]
    d.qpos[q] = DEFAULT
    mujoco.mj_forward(m, d)

    net = ActorCritic()
    net.load_state_dict(torch.load(ckpt, map_location="cpu")["net"]); net.eval()
    obs = np.zeros(45, dtype=np.float32); a_ = np.zeros(12, dtype=np.float32); tgt = DEFAULT.copy()

    peak_z, worst_up = -1e9, 1.0
    ramp_start = -0.35 * width
    n_steps = int(seconds / 0.02)
    for k in range(n_steps):
        for _ in range(4):
            d.ctrl[act] = clip_torque_speed(KP * (tgt - d.qpos[q]) - KD * d.qvel[dof], d.qvel[dof])
            mujoco.mj_step(m, d)
        obs[0:3] = d.qvel[bd+3:bd+6] * 0.25
        obs[3:6] = gravity(d.qpos[bq+3:bq+7])
        obs[6:9] = [1.0, 0.0, 0.0]
        obs[9:21] = d.qpos[q] - DEFAULT
        obs[21:33] = d.qvel[dof] * 0.05
        obs[33:45] = a_
        with torch.inference_mode():
            mu, _ = net(torch.as_tensor(obs).unsqueeze(0))
        a_ = mu.numpy()[0]
        tgt = DEFAULT + 0.25 * a_
        peak_z = max(peak_z, float(d.qpos[bq+2]))
        if k * 0.02 > 2.0:      # 跳过落地/起步瞬态
            worst_up = min(worst_up, float(d.xmat[bb].reshape(3, 3)[2, 2]))

    dist = float(np.hypot(d.qpos[bq] - x0, d.qpos[bq+1] - y0))
    climb = float(d.qpos[bq+2]) - (gz if gz else 0.0)
    final_up = float(d.xmat[bb].reshape(3, 3)[2, 2])
    return dict(slope=slope, dist=dist, climb=climb, up=worst_up, final_up=final_up,
                on_ramp=float(d.qpos[bq]) > ramp_start + 0.5,
                x=float(d.qpos[bq]), z=float(d.qpos[bq+2]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(BASE, "_ladder"))
    ap.add_argument("--glob", default="slope_*.xml")
    ap.add_argument("--ckpt", default=os.path.join(BASE, "ckpt", "bc.pt"))
    ap.add_argument("--seconds", type=float, default=8.0)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, a.glob)))
    print("%-12s %8s %8s %8s %8s %8s %s" % ("scene", "slope(deg)", "dist", "climb", "min_up", "end_up", "verdict"))
    for f in files:
        r = run_one(f, a.ckpt, a.seconds)
        if r is None:
            print("%-12s  加载失败" % os.path.basename(f))
            continue
        ok = "[OK] 能走" if (r["final_up"] > 0.8 and r["on_ramp"]) else "[FAIL] 摔/没上坡"
        print("%-12s %7.1f  %8.2f %8.2f %8.3f %8.3f %s" % (
            os.path.basename(f), r["slope"] if r["slope"] else 0.0,
            r["dist"], r["climb"], r["up"], r["final_up"], ok))


if __name__ == "__main__":
    main()
