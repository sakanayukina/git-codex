"""长时行走基准：跑最长时间，记录「存活时间 / 总里程 / 平均速度 / 是否摔」。

支持两种策略：
  --policy teacher   开源 TorchScript（pretrained/go2_cts_vanilla2_*.pt）
  --policy student   我们蒸馏的 ActorCritic（ckpt/bc.pt）

    python longrun_test.py --robot go2 --policy teacher --xml ../village_walk_final.xml --seconds 90
    python longrun_test.py --robot go2 --policy student --xml ../village_walk_final.xml --seconds 90
    python longrun_test.py --robot g1  --xml ../g1_village_final.xml --seconds 60 --at 0 -17.5
"""
import argparse
import os
import sys

import mujoco
import numpy as np
import torch

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "..", "_tools"))

from ppo import ActorCritic
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity
import g1_policy as g1p  # noqa: E402

GO2_JOINTS = ["FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
              "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
              "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
              "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint"]
G1_JOINTS = [
    "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
    "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
    "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
    "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
]


def build_index(m, root_name, joints):
    bb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, root_name)
    bj = next(j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE
              and int(m.jnt_bodyid[j]) == bb)
    bq, bd = int(m.jnt_qposadr[bj]), int(m.jnt_dofadr[bj])
    q, dof, act = [], [], []
    for jn in joints:
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn)
        q.append(int(m.jnt_qposadr[j])); dof.append(int(m.jnt_dofadr[j]))
        act.append(next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == j))
    return bb, bq, bd, np.array(q), np.array(dof), np.array(act)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--robot", choices=["go2", "g1"], default="go2")
    ap.add_argument("--policy", choices=["teacher", "student"], default="teacher")
    ap.add_argument("--xml", default=os.path.join(BASE, "..", "village_walk_final.xml"))
    ap.add_argument("--seconds", type=float, default=90.0)
    ap.add_argument("--at", nargs=2, type=float, default=None)
    ap.add_argument("--seeds", type=int, default=1, help="重复次数（不同初始扰动）")
    a = ap.parse_args()

    m = mujoco.MjModel.from_xml_path(a.xml)
    if a.robot == "go2":
        m.opt.timestep = 0.005
        root, joints, decim, default = "base", GO2_JOINTS, 4, DEFAULT
        kp = np.array(KP, dtype=np.float32); kd = np.array(KD, dtype=np.float32)
    else:
        m.opt.timestep = 0.002
        root, joints, decim, default = "pelvis", G1_JOINTS, 10, g1p.DEFAULT
        kp = np.array(g1p.KP, dtype=np.float32); kd = np.array(g1p.KD, dtype=np.float32)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)

    bb, bq, bd, q, dof, act = build_index(m, root, joints)
    ctrl_dt = m.opt.timestep * decim

    hf = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    gid = np.array([-1], dtype=np.int32); grp = np.ones(6, dtype=np.uint8)

    def ground(x, y):
        for dx, dy in [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2)]:
            dist = mujoco.mj_ray(m, d, np.array([x + dx, y + dy, 300.0]),
                                 np.array([0, 0, -1.0]), grp, 1, -1, gid)
            if dist > 0 and int(gid[0]) == hf:
                return 300.0 - dist
        return 5.0

    # 策略
    if a.robot == "go2" and a.policy == "teacher":
        net = torch.jit.load(os.path.join(BASE, "pretrained", "go2_cts_vanilla2_103.5k_0.5786.pt"))
        net.eval()
        kind = "ts"
    elif a.robot == "go2":
        net = ActorCritic()
        net.load_state_dict(torch.load(os.path.join(BASE, "ckpt", "bc.pt"), map_location="cpu")["net"])
        net.eval()
        kind = "ac"
    else:
        net = torch.jit.load(os.path.join(BASE, "..", "props", "robots", "g1", "motion.pt"))
        if hasattr(net, "reset_memory"):
            net.reset_memory()
        kind = "ts"

    spawn = a.at if a.at else ([1.0, -20.0] if a.robot == "go2" else [0.0, -17.5])
    print("robot=%s policy=%s scene=%s 目标 %.0f s x%d"
          % (a.robot, kind + "/" + a.policy, os.path.basename(a.xml), a.seconds, a.seeds))

    for seed in range(a.seeds):
        gz = ground(spawn[0], spawn[1])
        d.qpos[bq:bq+3] = [spawn[0], spawn[1], gz + (0.45 if a.robot == "go2" else 0.78)]
        d.qpos[bq+3:bq+7] = [1, 0, 0, 0]
        d.qpos[q] = default
        mujoco.mj_forward(m, d)
        if seed > 0:                      # 后续种子加一点初始扰动
            rng = np.random.default_rng(seed)
            d.qvel[bd:bd+6] = rng.normal(0, 0.05, 6)
        if a.robot == "g1" and hasattr(net, "reset_memory"):
            net.reset_memory()

        ndim = 45 if a.robot == "go2" else 47
        obs = np.zeros(ndim, dtype=np.float32)
        a_ = np.zeros(12, dtype=np.float32)
        tgt = np.asarray(default, dtype=np.float64).copy()
        x0, y0 = float(d.qpos[bq]), float(d.qpos[bq+1])
        survived, steps = 0.0, int(a.seconds / ctrl_dt)

        for k in range(steps):
            for _ in range(decim):
                qq, dq = d.qpos[q], d.qvel[dof]
                tau = kp * (tgt - qq) - kd * dq
                if a.robot == "go2":
                    d.ctrl[act] = clip_torque_speed(tau, dq)
                else:
                    d.ctrl[act] = np.clip(tau, -200, 200)
                mujoco.mj_step(m, d)

            up = float(d.xmat[bb].reshape(3, 3)[2, 2])
            survived = (k + 1) * ctrl_dt
            if up < 0.5:
                break

            # 观测
            if a.robot == "go2":
                obs[0:3] = d.qvel[bd+3:bd+6] * 0.25
                obs[3:6] = gravity(d.qpos[bq+3:bq+7])
                obs[6:9] = [1.0, 0.0, 0.0]
                obs[9:21] = d.qpos[q] - DEFAULT
                obs[21:33] = d.qvel[dof] * 0.05
                obs[33:45] = a_
                with torch.inference_mode():
                    out = net(torch.as_tensor(obs).unsqueeze(0))
                a_ = (out[0].numpy() if isinstance(out, tuple) else out.numpy())[0]
                tgt = DEFAULT + 0.25 * a_
            else:
                ph = (survived % g1p.PERIOD) / g1p.PERIOD
                obs[0:3] = d.qvel[bd+3:bd+6] * g1p.SCALE["ang_vel"]
                obs[3:6] = g1p.gravity_orientation(d.qpos[bq+3:bq+7])
                obs[6:9] = np.array([0.5, 0.0, 0.0]) * g1p.CMD_SCALE
                obs[9:21] = (d.qpos[q] - g1p.DEFAULT) * g1p.SCALE["dof_pos"]
                obs[21:33] = d.qvel[dof] * g1p.SCALE["dof_vel"]
                obs[33:45] = a_
                obs[45:47] = [np.sin(2*np.pi*ph), np.cos(2*np.pi*ph)]
                a_ = net(torch.from_numpy(obs).unsqueeze(0)).detach().numpy().flatten()[:12]
                tgt = np.asarray(g1p.DEFAULT) + g1p.SCALE["action"] * a_

        dist = float(np.hypot(d.qpos[bq] - x0, d.qpos[bq+1] - y0))
        fell = survived < a.seconds - 1e-6
        print("  seed %d: 存活 %5.1f s / %.0f s | 里程 %6.2f m | 均速 %.2f m/s | %s"
              % (seed, survived, a.seconds, dist, dist / max(survived, 1e-6),
                 "摔倒" if fell else "全程未摔"))


if __name__ == "__main__":
    main()
