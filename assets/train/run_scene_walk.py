"""在 demo_v32（完整村子展示场景）里看 Go2 和 G1 走路。

做法：物理分别在 `village_walk4.xml`（Go2）和 `g1_terrain_plain.xml`（G1）里闭环，
每一帧把两台机器人的位姿/关节角“镜像”到 demo_v32 的展示机器人上。
原因：demo_v32 里道具 body 数量太多，直接在那里跑策略机器人走不动（已在 AGENTS 记录）。

    python run_scene_walk.py                 # 开窗口看
    python run_scene_walk.py --headless 5    # 不开窗口，报位移
"""
import argparse
import os
import sys
import time

import mujoco
import numpy as np
import torch

from ppo import ActorCritic
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity

JOINTS = ["FL_hip", "FL_thigh", "FL_calf", "FR_hip", "FR_thigh", "FR_calf",
          "RL_hip", "RL_thigh", "RL_calf", "RR_hip", "RR_thigh", "RR_calf"]
BASE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(BASE, "..", "demo_v32.xml")
PHYS = os.path.join(BASE, "..", "village_walk4.xml")
G1_PHYS = os.path.join(BASE, "..", "g1_terrain_plain.xml")
G1_POLICY = os.path.join(BASE, "..", "props", "robots", "g1", "motion.pt")
G1_JOINTS = [
    "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
    "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
    "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
    "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
]

sys.path.insert(0, os.path.join(BASE, "..", "_tools"))
import g1_policy as g1p  # noqa: E402


def quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1*w2 - x1*x2 - y1*y2 - z1*z2,
                     w1*x2 + x1*w2 + y1*z2 - z1*y2,
                     w1*y2 - x1*z2 + y1*w2 + z1*x2,
                     w1*z2 + x1*y2 - y1*x2 + z1*w2])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", type=float, default=0.0)
    ap.add_argument("--follow", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--shot", default="", help="在指定秒数存一张图，如 3")
    a = ap.parse_args()

    # 展示模型（只用来看）
    dm = mujoco.MjModel.from_xml_path(DEMO)
    dd = mujoco.MjData(dm)
    mujoco.mj_forward(dm, dd)
    gid_body = mujoco.mj_name2id(dm, mujoco.mjtObj.mjOBJ_BODY, "go2_base")
    q0 = dm.body_quat[gid_body].copy()
    demo_jadr = [int(dm.jnt_qposadr[mujoco.mj_name2id(dm, mujoco.mjtObj.mjOBJ_JOINT, j + "_joint")])
                 for j in JOINTS]

    # 物理模型（策略闭环）
    m = mujoco.MjModel.from_xml_path(PHYS)
    m.opt.timestep = 0.005
    d = mujoco.MjData(m)
    bb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
    bj = next(j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE
              and int(m.jnt_bodyid[j]) == bb)
    bq, bd = int(m.jnt_qposadr[bj]), int(m.jnt_dofadr[bj])
    qadr, dadr, aid = [], [], []
    for jn in JOINTS:
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn + "_joint")
        qadr.append(int(m.jnt_qposadr[j])); dadr.append(int(m.jnt_dofadr[j]))
        aid.append(next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == j))
    qadr, dadr, aid = np.array(qadr), np.array(dadr), np.array(aid)

    hf = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    gid = np.array([-1], dtype=np.int32); grp = np.ones(6, dtype=np.uint8)
    x, y = 12.0, -18.0
    d.qpos[bq:bq+3] = [x + 500, y + 500, -800]
    mujoco.mj_forward(m, d)
    gz = 5.0
    for dx, dy in [(0,0),(2,0),(-2,0),(0,2),(0,-2)]:
        dist = mujoco.mj_ray(m, d, np.array([x+dx, y+dy, 300.0]), np.array([0,0,-1.0]), grp, 1, -1, gid)
        if dist > 0 and int(gid[0]) == hf:
            gz = 300.0 - dist; break
    d.qpos[bq:bq+3] = [x, y, gz + 0.45]
    d.qpos[bq+3:bq+7] = [1, 0, 0, 0]
    d.qpos[qadr] = DEFAULT
    mujoco.mj_forward(m, d)

    net = ActorCritic(); net.load_state_dict(torch.load(os.path.join(BASE, "ckpt", "bc.pt"), map_location="cpu")["net"]); net.eval()
    obs = np.zeros(45, dtype=np.float32); action = np.zeros(12, dtype=np.float32); target = DEFAULT.copy()
    x0 = float(d.qpos[bq]); y0 = float(d.qpos[bq+1])

    # G1 物理孪生：官方 12 自由度平地策略，在 H1 台地平整区闭环。
    gm = mujoco.MjModel.from_xml_path(G1_PHYS)
    gm.opt.timestep = 0.002
    gd = mujoco.MjData(gm)
    if gm.nkey > 0:
        mujoco.mj_resetDataKeyframe(gm, gd, 0)
    g1x, g1y = 15.0, -14.0
    ghf = next(g for g in range(gm.ngeom) if gm.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    gd.qpos[0:3] = [g1x + 500.0, g1y + 500.0, -800.0]
    mujoco.mj_forward(gm, gd)
    g1gz = 0.8
    for dx, dy in [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2)]:
        dist = mujoco.mj_ray(
            gm, gd, np.array([g1x + dx, g1y + dy, 300.0]),
            np.array([0.0, 0.0, -1.0]), grp, 1, -1, gid)
        if dist > 0 and int(gid[0]) == ghf:
            g1gz = 300.0 - dist
            break
    gd.qpos[0:3] = [g1x, g1y, g1gz + 0.78]
    gd.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    gd.qpos[7:19] = g1p.DEFAULT
    mujoco.mj_forward(gm, gd)
    if gm.nq != 19 or gm.nu != 12:
        raise RuntimeError(f"G1 model mismatch: nq={gm.nq}, nu={gm.nu}")

    g1_net = torch.jit.load(G1_POLICY)
    if hasattr(g1_net, "reset_memory"):
        g1_net.reset_memory()
    g1_body = mujoco.mj_name2id(gm, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
    g1_demo_body = mujoco.mj_name2id(dm, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
    g1_demo_q0 = dm.body_quat[g1_demo_body].copy()
    g1_demo_jadr = [
        int(dm.jnt_qposadr[mujoco.mj_name2id(dm, mujoco.mjtObj.mjOBJ_JOINT, name)])
        for name in G1_JOINTS
    ]
    g1_qadr = np.array([
        int(gm.jnt_qposadr[mujoco.mj_name2id(gm, mujoco.mjtObj.mjOBJ_JOINT, name)])
        for name in G1_JOINTS
    ])
    g1_dadr = np.array([
        int(gm.jnt_dofadr[mujoco.mj_name2id(gm, mujoco.mjtObj.mjOBJ_JOINT, name)])
        for name in G1_JOINTS
    ])
    g1_default = np.array(g1p.DEFAULT, dtype=np.float32)
    g1_kp = np.array(g1p.KP, dtype=np.float32)
    g1_kd = np.array(g1p.KD, dtype=np.float32)
    g1_cmd = np.array([0.5, 0.0, 0.0], dtype=np.float32)
    g1_action = np.zeros(g1p.NUM_ACT, dtype=np.float32)
    g1_target = g1_default.copy()
    g1_obs = np.zeros(g1p.NUM_OBS, dtype=np.float32)
    g1_step_i = 0
    g1x0 = float(gd.qpos[0]); g1y0 = float(gd.qpos[1])

    def step_all():
        nonlocal obs, action, target, g1_action, g1_target, g1_obs, g1_step_i
        for _ in range(4):
            q, qd = d.qpos[qadr], d.qvel[dadr]
            d.ctrl[aid] = clip_torque_speed(KP*(target-q) - KD*qd, qd)
            mujoco.mj_step(m, d)
        obs[0:3] = d.qvel[bd+3:bd+6]*0.25
        obs[3:6] = gravity(d.qpos[bq+3:bq+7])
        obs[6:9] = [1.0, 0.0, 0.0]
        obs[9:21] = d.qpos[qadr] - DEFAULT
        obs[21:33] = d.qvel[dadr]*0.05
        obs[33:45] = action
        with torch.inference_mode():
            mu, _ = net(torch.as_tensor(obs).unsqueeze(0))
        action = mu.numpy()[0]; target = DEFAULT + 0.25*action

        # G1: 10 x 2 ms = 0.02 s；每 10 个子步执行一次 50 Hz 策略。
        for _ in range(10):
            g1_q = gd.qpos[g1_qadr]
            g1_dq = gd.qvel[g1_dadr]
            gd.ctrl[:] = np.clip(
                g1_kp * (g1_target - g1_q) - g1_kd * g1_dq, -200, 200)
            mujoco.mj_step(gm, gd)
            g1_step_i += 1
        with torch.inference_mode():
            t = g1_step_i * gm.opt.timestep
            ph = (t % g1p.PERIOD) / g1p.PERIOD
            g1_obs[0:3] = gd.qvel[3:6] * g1p.SCALE["ang_vel"]
            g1_obs[3:6] = g1p.gravity_orientation(gd.qpos[3:7])
            g1_obs[6:9] = g1_cmd * g1p.CMD_SCALE
            g1_obs[9:21] = (
                gd.qpos[g1_qadr] - g1_default) * g1p.SCALE["dof_pos"]
            g1_obs[21:33] = (
                gd.qvel[g1_dadr] * g1p.SCALE["dof_vel"])
            g1_obs[33:45] = g1_action
            g1_obs[45:47] = [
                np.sin(2 * np.pi * ph), np.cos(2 * np.pi * ph)]
            g1_action = g1_net(
                torch.from_numpy(g1_obs).unsqueeze(0)
            ).numpy().flatten()[:g1p.NUM_ACT]
            g1_target = g1_default + g1p.SCALE["action"] * g1_action

        # 镜像到展示模型
        dm.body_pos[gid_body] = d.qpos[bq:bq+3]
        dm.body_quat[gid_body] = quat_mul(q0, d.qpos[bq+3:bq+7])
        for k, adr in enumerate(demo_jadr):
            dd.qpos[adr] = d.qpos[qadr[k]]
        dm.body_pos[g1_demo_body] = gd.qpos[0:3]
        dm.body_quat[g1_demo_body] = quat_mul(g1_demo_q0, gd.qpos[3:7])
        for k, adr in enumerate(g1_demo_jadr):
            dd.qpos[adr] = gd.qpos[g1_qadr[k]]
        mujoco.mj_forward(dm, dd)

    if a.shot:
        sec = float(a.shot)
        for _ in range(int(sec / 0.02)):
            step_all()
        ren = mujoco.Renderer(dm, 360, 640)
        cam = mujoco.MjvCamera(); mujoco.mjv_defaultFreeCamera(dm, cam)
        cam.lookat[:] = 0.5 * (dd.xpos[gid_body] + dd.xpos[g1_demo_body])
        cam.distance, cam.azimuth, cam.elevation = 8.0, 0, -30
        ren.update_scene(dd, camera=cam)
        from pngutil import save_rgb
        os.makedirs("shots", exist_ok=True)
        out = os.path.join("shots", "scene_walk_t%.1f.png" % sec)
        save_rgb(ren.render(), out)
        go2_dist = float(np.hypot(
            dd.xpos[gid_body][0] - x0, dd.xpos[gid_body][1] - y0))
        g1_dist = float(np.hypot(
            dd.xpos[g1_demo_body][0] - g1x0,
            dd.xpos[g1_demo_body][1] - g1y0))
        print(f"saved {out}; distance Go2={go2_dist:.2f} m G1={g1_dist:.2f} m")
        return

    if a.headless > 0:
        for _ in range(int(a.headless / 0.02)):
            step_all()
        go2_dist = float(np.hypot(
            dd.xpos[gid_body][0] - x0, dd.xpos[gid_body][1] - y0))
        g1_dist = float(np.hypot(
            dd.xpos[g1_demo_body][0] - g1x0,
            dd.xpos[g1_demo_body][1] - g1y0))
        print(
            f"display distance Go2={go2_dist:.2f} m "
            f"(z={dd.xpos[gid_body][2]:.2f}), "
            f"G1={g1_dist:.2f} m (z={dd.xpos[g1_demo_body][2]:.2f})")
        return

    with mujoco.viewer.launch_passive(dm, dd) as v:
        v.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        v.cam.distance = 8.0
        v.cam.azimuth = 0
        v.cam.elevation = -30
        v.cam.lookat[:] = 0.5 * (dd.xpos[gid_body] + dd.xpos[g1_demo_body])
        t_next = time.perf_counter()
        while v.is_running():
            step_all()
            if a.follow:
                v.cam.lookat[:] = 0.5 * (
                    dd.xpos[gid_body] + dd.xpos[g1_demo_body])
            v.sync()
            t_next += 0.02
            dt = t_next - time.perf_counter()
            time.sleep(dt) if dt > 0 else None
            if dt <= 0:
                t_next = time.perf_counter()


if __name__ == "__main__":
    main()
