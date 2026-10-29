"""在 village_duo.xml（Go2 + G1 同一物理世界）里同时驱动两台机器人。

    python run_duo.py --seconds 8            # headless，报两台位移/倾角/间距
    python run_duo.py --shot 6               # 存图（直接渲染 village_duo：地形+机器人，无房子外观）
    python run_duo.py --go2-at 5 -24 --g1-at 0 -17.5
"""
import argparse
import os
import sys

import mujoco
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ppo import ActorCritic
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_tools"))
import g1_policy as g1p  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
XML = os.path.join(BASE, "..", "village_duo.xml")
GO2_CKPT = os.path.join(BASE, "ckpt", "bc.pt")
GO2_TEACHER = os.path.join(BASE, "pretrained", "go2_cts_vanilla2_103.5k_0.5786.pt")
G1_POLICY = os.path.join(BASE, "..", "props", "robots", "g1", "motion.pt")

GO2_JOINTS = ["FL_hip", "FL_thigh", "FL_calf", "FR_hip", "FR_thigh", "FR_calf",
              "RL_hip", "RL_thigh", "RL_calf", "RR_hip", "RR_thigh", "RR_calf"]
G1_JOINTS = [
    "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
    "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
    "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
    "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
]


def find_freejoint(m, body):
    for j in range(m.njnt):
        if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE and int(m.jnt_bodyid[j]) == body:
            return j
    raise SystemExit("找不到 body %s 的 freejoint" % body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--go2-policy", choices=["teacher", "student"], default="teacher")
    ap.add_argument("--go2-at", nargs=2, type=float, default=[5.0, -24.0])
    ap.add_argument("--g1-at", nargs=2, type=float, default=[0.0, -17.5])
    ap.add_argument("--shot", type=float, default=0.0)
    ap.add_argument("--timestep", type=float, default=0.002)
    ap.add_argument("--substeps", type=int, default=10,
                    help="每个 50 Hz 控制周期的物理子步数")
    a = ap.parse_args()

    m = mujoco.MjModel.from_xml_path(XML)
    m.opt.timestep = a.timestep
    ctrl_dt = a.timestep * a.substeps
    d = mujoco.MjData(m)

    # Go2 索引
    g2b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
    g2fj = find_freejoint(m, g2b)
    g2q0, g2d0 = int(m.jnt_qposadr[g2fj]), int(m.jnt_dofadr[g2fj])
    g2q = [int(m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, j + "_joint")]) for j in GO2_JOINTS]
    g2dof = [int(m.jnt_dofadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, j + "_joint")]) for j in GO2_JOINTS]
    g2a = [next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, j + "_joint")) for j in GO2_JOINTS]

    # G1 索引
    g1b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
    g1fj = find_freejoint(m, g1b)
    g1q0, g1d0 = int(m.jnt_qposadr[g1fj]), int(m.jnt_dofadr[g1fj])
    g1q = [int(m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, j)]) for j in G1_JOINTS]
    g1dof = [int(m.jnt_dofadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, j)]) for j in G1_JOINTS]
    g1a = [next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, j)) for j in G1_JOINTS]

    # 贴地出生
    hf = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    gid = np.array([-1], dtype=np.int32); grp = np.ones(6, dtype=np.uint8)

    def ground(x, y):
        for dx, dy in [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2)]:
            dist = mujoco.mj_ray(m, d, np.array([x + dx, y + dy, 300.0]),
                                 np.array([0, 0, -1.0]), grp, 1, -1, gid)
            if dist > 0 and int(gid[0]) == hf:
                return 300.0 - dist
        return 5.0

    g2gz = ground(*a.go2_at)
    d.qpos[g2q0:g2q0+3] = [a.go2_at[0], a.go2_at[1], g2gz + 0.45]
    d.qpos[g2q0+3:g2q0+7] = [1, 0, 0, 0]
    d.qpos[g2q] = DEFAULT

    g1gz = ground(*a.g1_at)
    d.qpos[g1q0:g1q0+3] = [a.g1_at[0], a.g1_at[1], g1gz + 0.78]
    d.qpos[g1q0+3:g1q0+7] = [1, 0, 0, 0]
    d.qpos[g1q] = g1p.DEFAULT
    mujoco.mj_forward(m, d)

    # 策略
    if a.go2_policy == "teacher":
        g2net = torch.jit.load(GO2_TEACHER)
    else:
        g2net = ActorCritic()
        g2net.load_state_dict(torch.load(GO2_CKPT, map_location="cpu")["net"])
    g2net.eval()
    g1net = torch.jit.load(G1_POLICY)
    if hasattr(g1net, "reset_memory"):
        g1net.reset_memory()

    g2_obs = np.zeros(45, dtype=np.float32); g2_act = np.zeros(12, dtype=np.float32)
    g2_tgt = DEFAULT.copy()
    g1_obs = np.zeros(47, dtype=np.float32); g1_act = np.zeros(12, dtype=np.float32)
    g1_tgt = np.asarray(g1p.DEFAULT, dtype=np.float64).copy()
    g1_kp = np.array(g1p.KP, dtype=np.float32); g1_kd = np.array(g1p.KD, dtype=np.float32)
    g1_cmd = np.array([0.5, 0.0, 0.0], dtype=np.float32)
    g1_step = 0

    n_ctrl = int(a.seconds / ctrl_dt)
    min_sep = 1e9
    g2x0, g2y0 = float(d.qpos[g2q0]), float(d.qpos[g2q0+1])
    g1x0, g1y0 = float(d.qpos[g1q0]), float(d.qpos[g1q0+1])

    for k in range(n_ctrl):
        # 默认 20 × 0.001 = 0.02 s，两台在同一 mj_step 里推进
        for _ in range(a.substeps):
            q = d.qpos[g2q]; qd = d.qvel[g2dof]
            d.ctrl[g2a] = clip_torque_speed(KP * (g2_tgt - q) - KD * qd, qd)
            q1 = d.qpos[g1q]; qd1 = d.qvel[g1dof]
            d.ctrl[g1a] = np.clip(g1_kp * (g1_tgt - q1) - g1_kd * qd1, -200, 200)
            mujoco.mj_step(m, d)

        # Go2 观测/策略
        g2_obs[0:3] = d.qvel[g2d0+3:g2d0+6] * 0.25
        g2_obs[3:6] = gravity(d.qpos[g2q0+3:g2q0+7])
        g2_obs[6:9] = [1.0, 0.0, 0.0]
        g2_obs[9:21] = d.qpos[g2q] - DEFAULT
        g2_obs[21:33] = d.qvel[g2dof] * 0.05
        g2_obs[33:45] = g2_act
        with torch.inference_mode():
            out = g2net(torch.as_tensor(g2_obs).unsqueeze(0))
        g2_act = (out[0].numpy() if isinstance(out, tuple) else out.numpy())[0]
        g2_tgt = DEFAULT + 0.25 * g2_act

        # G1 观测/策略
        ph = (g1_step * ctrl_dt % g1p.PERIOD) / g1p.PERIOD
        g1_obs[0:3] = d.qvel[g1d0+3:g1d0+6] * g1p.SCALE["ang_vel"]
        g1_obs[3:6] = g1p.gravity_orientation(d.qpos[g1q0+3:g1q0+7])
        g1_obs[6:9] = g1_cmd * g1p.CMD_SCALE
        g1_obs[9:21] = (d.qpos[g1q] - g1p.DEFAULT) * g1p.SCALE["dof_pos"]
        g1_obs[21:33] = d.qvel[g1dof] * g1p.SCALE["dof_vel"]
        g1_obs[33:45] = g1_act
        g1_obs[45:47] = [np.sin(2*np.pi*ph), np.cos(2*np.pi*ph)]
        g1_act = g1net(torch.from_numpy(g1_obs).unsqueeze(0)).detach().numpy().flatten()[:g1p.NUM_ACT]
        g1_tgt = np.asarray(g1p.DEFAULT) + g1p.SCALE["action"] * g1_act
        g1_step += 1

        sep = float(np.hypot(d.xpos[g2b][0]-d.xpos[g1b][0], d.xpos[g2b][1]-d.xpos[g1b][1]))
        min_sep = min(min_sep, sep)

    g2_up = float(d.xmat[g2b].reshape(3, 3)[2, 2])
    g1_up = float(d.xmat[g1b].reshape(3, 3)[2, 2])
    print("Go2: 位移 %.2f m | up=%.3f" % (float(np.hypot(d.qpos[g2q0]-g2x0, d.qpos[g2q0+1]-g2y0)), g2_up))
    print("G1 : 位移 %.2f m | up=%.3f" % (float(np.hypot(d.qpos[g1q0]-g1x0, d.qpos[g1q0+1]-g1y0)), g1_up))
    print("两机最小间距 %.2f m" % min_sep)

    if a.shot > 0:
        for _ in range(int((a.shot - a.seconds) / 0.02)):
            mujoco.mj_step(m, d)
        ren = mujoco.Renderer(m, 720, 1280)
        cam = mujoco.MjvCamera(); mujoco.mjv_defaultFreeCamera(m, cam)
        cam.lookat[:] = 0.5 * (d.xpos[g2b] + d.xpos[g1b])
        cam.distance, cam.azimuth, cam.elevation = 15.0, 135, -20
        ren.update_scene(d, camera=cam)
        from pngutil import save_rgb
        os.makedirs("shots", exist_ok=True)
        save_rgb(ren.render(), os.path.join("shots", "duo_t%.0f.png" % a.shot))
        print("存图 shots/duo_t%.0f.png" % a.shot)


if __name__ == "__main__":
    main()
