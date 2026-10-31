"""两台 Go2 在同一物理世界（village_duo_go2x2.xml）验证真实碰撞：
机器人1 朝 +x 行走，机器人2 原地静止（不驱动、当障碍物），机器人1 会撞上它并被挡住。

    python run_duo_go2x2.py --seconds 6 --gap 1.3
"""
import argparse
import os
import sys

import mujoco

import terrain_road
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ppo import ActorCritic
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity

BASE = os.path.dirname(os.path.abspath(__file__))
XML = os.path.join(BASE, "..", "village_duo_go2x2.xml")
CKPT = os.path.join(BASE, "ckpt", "bc.pt")
LEGS = ["FL", "FR", "RL", "RR"]
SEGS = ["hip", "thigh", "calf"]


def robot_index(m, prefix):
    body = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base" + prefix)
    fj = next(j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE
              and int(m.jnt_bodyid[j]) == body)
    q0, d0 = int(m.jnt_qposadr[fj]), int(m.jnt_dofadr[fj])
    q, dof, act = [], [], []
    for L in LEGS:
        for S in SEGS:
            j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "%s%s_%s_joint" % (L, prefix, S))
            q.append(int(m.jnt_qposadr[j]))
            dof.append(int(m.jnt_dofadr[j]))
            act.append(next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == j))
    return body, q0, d0, np.array(q), np.array(dof), np.array(act)


def subtree(m, root):
    kids = {}
    for i in range(m.nbody):
        kids.setdefault(int(m.body_parentid[i]), []).append(i)
    out, st = set(), [root]
    while st:
        b = st.pop()
        out.add(b)
        st.extend(kids.get(b, []))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--gap", type=float, default=1.3)
    a = ap.parse_args()

    m = terrain_road.load_model(XML)
    m.opt.timestep = 0.005
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)  # 先 forward，raycast 才能拿到 geom 位置

    b1, q10, d10, q1, dof1, a1 = robot_index(m, "")
    b2, q20, d20, q2, dof2, a2 = robot_index(m, "2")
    sub1, sub2 = subtree(m, b1), subtree(m, b2)

    hf = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    gid = np.array([-1], dtype=np.int32); grp = np.ones(6, dtype=np.uint8)

    def ground(x, y):
        for dx, dy in [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2)]:
            dist = mujoco.mj_ray(m, d, np.array([x + dx, y + dy, 300.0]),
                                 np.array([0, 0, -1.0]), grp, 1, -1, gid)
            if dist > 0 and int(gid[0]) == hf:
                return 300.0 - dist
        return 5.0

    y = -20.0
    gz = ground(0.0, y)
    d.qpos[q10:q10+3] = [0.0, y, gz + 0.45]; d.qpos[q10+3:q10+7] = [1, 0, 0, 0]; d.qpos[q1] = DEFAULT
    d.qpos[q20:q20+3] = [a.gap, y, gz + 0.45]; d.qpos[q20+3:q20+7] = [1, 0, 0, 0]; d.qpos[q2] = DEFAULT
    x2_start = a.gap
    mujoco.mj_forward(m, d)
    print("地面 %.2f m，出生 z=%.2f（间距 %.1f m）" % (gz, gz + 0.45, a.gap))

    net = ActorCritic()
    net.load_state_dict(torch.load(CKPT, map_location="cpu")["net"]); net.eval()
    obs = np.zeros(45, dtype=np.float32); act = np.zeros(12, dtype=np.float32); tgt = DEFAULT.copy()

    min_sep, contact = 1e9, 0
    n_ctrl = int(a.seconds / 0.02)

    for k in range(n_ctrl):
        for _ in range(4):
            d.ctrl[a1] = clip_torque_speed(KP * (tgt - d.qpos[q1]) - KD * d.qvel[dof1], d.qvel[dof1])
            d.ctrl[a2] = 0.0  # 第二台静止当障碍物
            mujoco.mj_step(m, d)
        obs[0:3] = d.qvel[d10+3:d10+6] * 0.25
        obs[3:6] = gravity(d.qpos[q10+3:q10+7])
        obs[6:9] = [1.0, 0.0, 0.0]
        obs[9:21] = d.qpos[q1] - DEFAULT
        obs[21:33] = d.qvel[dof1] * 0.05
        obs[33:45] = act
        with torch.inference_mode():
            mu, _ = net(torch.as_tensor(obs).unsqueeze(0))
        act = mu.numpy()[0]
        tgt = DEFAULT + 0.25 * act

        sep = float(np.hypot(d.xpos[b1][0]-d.xpos[b2][0], d.xpos[b1][1]-d.xpos[b2][1]))
        min_sep = min(min_sep, sep)
        for c in d.contact[:d.ncon]:
            bb1, bb2 = int(m.geom_bodyid[int(c.geom1)]), int(m.geom_bodyid[int(c.geom2)])
            if (bb1 in sub1 and bb2 in sub2) or (bb1 in sub2 and bb2 in sub1):
                contact += 1
                break

    print("机器人1（行走）末 x=%.2f（起 0.00，无阻挡时约走 2.8 m）" % d.qpos[q10])
    print("机器人2（静止）末 x=%.2f（起 %.2f，被推 %.2f m）" % (d.qpos[q20], x2_start, x2_start - d.qpos[q20]))
    print("两机最小间距 %.2f m | 互碰控制步 %d/%d" % (min_sep, contact, n_ctrl))
    print("up1=%.3f up2=%.3f" %
          (float(d.xmat[b1].reshape(3,3)[2,2]), float(d.xmat[b2].reshape(3,3)[2,2])))


if __name__ == "__main__":
    main()
