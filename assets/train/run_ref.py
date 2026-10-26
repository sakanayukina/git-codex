"""在作者模型（去外观 mesh）上跑他的策略：力矩控制 + 转速包络，可选存图。

    python run_ref.py --xml ref/mjcf/terrain_100.xml --cmd-x 1.0 --z0 0.45 --shots 1,4,7,9.5
"""
import argparse

import mujoco
import numpy as np
import torch

from pngutil import save_rgb

JOINTS = ["FL_hip", "FL_thigh", "FL_calf", "FR_hip", "FR_thigh", "FR_calf",
          "RL_hip", "RL_thigh", "RL_calf", "RR_hip", "RR_thigh", "RR_calf"]
DEFAULT = np.array([0.1, 0.8, -1.5, -0.1, 0.8, -1.5, 0.1, 1.0, -1.5, -0.1, 1.0, -1.5],
                   dtype=np.float32)
KP = np.full(12, 25.0, dtype=np.float32)
KD = np.full(12, 0.5, dtype=np.float32)
CMD_SCALE = np.array([0.5, 1.0, 1.0], dtype=np.float32)
ANG_SCALE, DOF_POS_SCALE, DOF_VEL_SCALE, ACTION_SCALE = 0.25, 1.0, 0.05, 0.25
MOTOR = dict(X1=13.5, X2=30.0, Y1=20.2, Y2=23.4)


def clip_torque_speed(effort, qd):
    same = qd * effort > 0.0
    max_e = np.where(same, MOTOR["Y1"], MOTOR["Y2"])
    high = max_e * (1.0 - (np.abs(qd) - MOTOR["X1"]) / (MOTOR["X2"] - MOTOR["X1"]))
    max_e = np.where(np.abs(qd) < MOTOR["X1"], max_e, np.maximum(high, 0.0))
    return np.clip(effort, -max_e, max_e)


def gravity(q):
    qw, qx, qy, qz = q
    return np.array([2 * (-qz * qx + qw * qy),
                     -2 * (qz * qy + qw * qx),
                     1 - 2 * (qw * qw + qz * qz)], dtype=np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default="ref/mjcf/flat_nomesh.xml")
    ap.add_argument("--policy", default="pretrained/go2_cts_vanilla2_103.5k_0.5786.pt")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--cmd-x", type=float, default=-1.0)
    ap.add_argument("--z0", type=float, default=0.32)
    ap.add_argument("--shots", default="")
    a = ap.parse_args()

    m = mujoco.MjModel.from_xml_path(a.xml)
    m.opt.timestep = 0.005
    d = mujoco.MjData(m)
    d.qpos[3:7] = [1, 0, 0, 0]
    qadr, dadr, aid = [], [], []
    for jn in JOINTS:
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn + "_joint")
        qadr.append(int(m.jnt_qposadr[j]))
        dadr.append(int(m.jnt_dofadr[j]))
        aid.append(next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == j))
    qadr, dadr, aid = np.array(qadr), np.array(dadr), np.array(aid)
    # 基座位姿/速度：定位 base body 的 free joint（村里 qvel[0:3] 属于瓦砾，不是机器人）
    bb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
    bj = next(j for j in range(m.njnt)
              if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE and int(m.jnt_bodyid[j]) == bb)
    bq, bd = int(m.jnt_qposadr[bj]), int(m.jnt_dofadr[bj])
    d.qpos[bq:bq + 3] = [d.qpos[bq], d.qpos[bq + 1], a.z0]
    d.qpos[qadr] = DEFAULT
    mujoco.mj_forward(m, d)

    pol = torch.jit.load(a.policy)
    pol.eval()
    if hasattr(pol, "reset"):
        pol.reset()

    shots = sorted(float(x) for x in a.shots.split(",") if x.strip())
    renderer = cam = None
    if shots:
        import os
        os.makedirs("shots", exist_ok=True)
        renderer = mujoco.Renderer(m, 360, 640)
        cam = mujoco.MjvCamera()
        mujoco.mjv_defaultFreeCamera(m, cam)
        cam.distance, cam.azimuth, cam.elevation = 2.6, 135, -18

    target = DEFAULT.copy()
    action = np.zeros(12, dtype=np.float32)
    obs = np.zeros(45, dtype=np.float32)
    steps = int(a.seconds / (m.opt.timestep * 4))
    x0 = float(d.qpos[bq])
    vxs = []
    for i in range(steps):
        for _ in range(4):
            q, qd = d.qpos[qadr], d.qvel[dadr]
            eff = KP * (target - q) - KD * qd
            d.ctrl[aid] = clip_torque_speed(eff, qd)
            mujoco.mj_step(m, d)
        obs[0:3] = d.qvel[bd + 3:bd + 6] * ANG_SCALE
        obs[3:6] = gravity(d.qpos[bq + 3:bq + 7])
        obs[6:9] = np.array([0.5, 0.0, 0.0], dtype=np.float32) * CMD_SCALE
        if a.cmd_x > 0:
            obs[6] = a.cmd_x
        obs[9:21] = (d.qpos[qadr] - DEFAULT) * DOF_POS_SCALE
        obs[21:33] = d.qvel[dadr] * DOF_VEL_SCALE
        obs[33:45] = action
        with torch.inference_mode():
            out = pol(torch.as_tensor(obs).unsqueeze(0))
        action = (out[0] if isinstance(out, tuple) else out).numpy().flatten()[:12]
        action = np.clip(action, -100.0, 100.0)
        target = DEFAULT + ACTION_SCALE * action
        vxs.append(float(d.qvel[bd]))
        if shots and float(d.time) >= shots[0]:
            t = shots.pop(0)
            cam.lookat[:] = [float(d.qpos[bq]), float(d.qpos[bq + 1]), float(d.qpos[bq + 2])]
            renderer.update_scene(d, camera=cam)
            save_rgb(renderer.render(), "shots/walk_t%04.1f.png" % t)
        up = float(d.xmat[bb].reshape(3, 3)[2, 2])
        if up < 0.6:
            print("  第 %d 步摔倒（%.1f 秒）" % (i, i * 0.02))
            break
    dist = float(np.hypot(d.qpos[bq] - x0, d.qpos[bq + 1] - d.qpos[bq + 1]))
    print("位移 %.2f m | 平均 vx %.2f m/s | 末态 z %.2f | 时长 %.1f s"
          % (dist, float(np.mean(vxs)), float(d.qpos[bq + 2]), len(vxs) * 0.02))


if __name__ == "__main__":
    main()
