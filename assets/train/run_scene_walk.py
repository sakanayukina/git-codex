"""在 demo_v32（完整村子展示场景）里看机器狗走路。

做法：物理在轻量场景 `village_walk4.xml`（同款地形 + 同一台 Go2，策略闭环）里跑，
每一帧把机器人的位姿/关节角“镜像”到 demo_v32 的展示机器人上。
原因：demo_v32 里道具 body 数量太多，直接在那里跑策略机器人走不动（已在 AGENTS 记录）。

    python run_scene_walk.py                 # 开窗口看
    python run_scene_walk.py --headless 5    # 不开窗口，报位移
"""
import argparse
import os
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
    ap.add_argument("--cli", type=float, default=8.0, help="可走距离（米）")
    ap.add_argument("--follow", action="store_true")
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

    def step_all():
        nonlocal obs, action, target
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
        # 镜像到展示模型
        dm.body_pos[gid_body] = d.qpos[bq:bq+3]
        dm.body_quat[gid_body] = quat_mul(q0, d.qpos[bq+3:bq+7])
        for k, adr in enumerate(demo_jadr):
            dd.qpos[adr] = d.qpos[qadr[k]]
        mujoco.mj_forward(dm, dd)

    if a.shot:
        sec = float(a.shot)
        for _ in range(int(sec / 0.02)):
            step_all()
        ren = mujoco.Renderer(dm, 360, 640)
        cam = mujoco.MjvCamera(); mujoco.mjv_defaultFreeCamera(dm, cam)
        cam.lookat[:] = dd.xpos[gid_body]
        cam.distance, cam.azimuth, cam.elevation = 7.0, 135, -18
        ren.update_scene(dd, camera=cam)
        from pngutil import save_rgb
        os.makedirs("shots", exist_ok=True)
        out = os.path.join("shots", "scene_walk_t%.1f.png" % sec)
        save_rgb(ren.render(), out)
        print("存图", out, "；展示模型位移 %.2f m" % float(np.hypot(dd.xpos[gid_body][0]-x0, dd.xpos[gid_body][1]-y0)))
        return

    if a.headless > 0:
        for _ in range(int(a.headless / 0.02)):
            step_all()
        dist = float(np.hypot(dd.xpos[gid_body][0] - x0, dd.xpos[gid_body][1] - y0))
        print("展示模型里 go2_base 位移 %.2f m（末 x=%.2f z=%.2f）" % (dist, dd.xpos[gid_body][0], dd.xpos[gid_body][2]))
        return

    with mujoco.viewer.launch_passive(dm, dd) as v:
        v.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        v.cam.distance = 8.0
        v.cam.azimuth = 135
        v.cam.elevation = -18
        v.cam.lookat[:] = dd.xpos[gid_body]
        t_next = time.perf_counter()
        for _ in range(int(a.cli / 0.5) * 1000):
            if not v.is_running():
                break
            step_all()
            if a.follow:
                v.cam.lookat[:] = dd.xpos[gid_body]
            v.sync()
            t_next += 0.02
            dt = t_next - time.perf_counter()
            time.sleep(dt) if dt > 0 else None
            if dt <= 0:
                t_next = time.perf_counter()


if __name__ == "__main__":
    main()
