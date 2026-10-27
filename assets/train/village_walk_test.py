"""把训练好的策略（train/ckpt/bc.pt）放进村子场景，测它能走多远。

    python village_walk_test.py --xml ../village_walk.xml --seconds 10
"""
import argparse
import os

import mujoco
import numpy as np
import torch

from pngutil import save_rgb
from ppo import ActorCritic
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity

JOINTS = ["FL_hip", "FL_thigh", "FL_calf", "FR_hip", "FR_thigh", "FR_calf",
          "RL_hip", "RL_thigh", "RL_calf", "RR_hip", "RR_thigh", "RR_calf"]
CMD = np.array([1.0, 0.0, 0.0], dtype=np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default="../village_walk.xml")
    ap.add_argument("--ckpt", default="ckpt/bc.pt")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--shots", default="")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--at", nargs=2, type=float, default=None, help="出生 x y")
    a = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = ActorCritic().to(dev)
    net.load_state_dict(torch.load(a.ckpt, map_location=dev)["net"])
    net.eval()
    print("策略:", a.ckpt)

    m = mujoco.MjModel.from_xml_path(a.xml)
    m.opt.timestep = 0.005
    d = mujoco.MjData(m)
    qadr, dadr, aid = [], [], []
    for jn in JOINTS:
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn + "_joint")
        qadr.append(int(m.jnt_qposadr[j])); dadr.append(int(m.jnt_dofadr[j]))
        aid.append(next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == j))
    qadr, dadr, aid = np.array(qadr), np.array(dadr), np.array(aid)
    bb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
    bj = next(j for j in range(m.njnt)
              if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE and int(m.jnt_bodyid[j]) == bb)
    bq, bd = int(m.jnt_qposadr[bj]), int(m.jnt_dofadr[bj])

    mujoco.mj_resetData(m, d)
    gx, gy = (a.at if a.at else [12.0, -18.0])
    d.qpos[bq:bq + 3] = [gx, gy, 60.0]
    mujoco.mj_forward(m, d)
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tools"))
    try:
        from polish import terrain_fn
        tk = terrain_fn(os.path.abspath(a.xml))
        gz = float(tk(gx, gy))
    except Exception as e:
        print("  (terrain_fn 不可用，退回 5.0)", e)
        gz = 5.0
    d.qpos[bq:bq + 3] = [gx, gy, gz + 0.45]
    print("出生 (%.1f, %.1f) 地面 %.2f" % (gx, gy, gz))
    d.qpos[bq + 3:bq + 7] = [1, 0, 0, 0]
    d.qpos[qadr] = DEFAULT
    mujoco.mj_forward(m, d)

    shots = sorted(float(x) for x in a.shots.split(",") if x.strip())
    renderer = cam = None
    if shots:
        os.makedirs("shots", exist_ok=True)
        renderer = mujoco.Renderer(m, 360, 640)
        cam = mujoco.MjViewer if False else mujoco.MjvCamera()
        mujoco.mjv_defaultFreeCamera(m, cam)
        cam.distance, cam.azimuth, cam.elevation = 6.0, 135, -20

    target = DEFAULT.copy()
    action = np.zeros(12, dtype=np.float32)
    obs = np.zeros(45, dtype=np.float32)
    steps = int(a.seconds / 0.02)
    x0, y0 = float(d.qpos[bq]), float(d.qpos[bq + 1])
    vxs, up_now = [], 1.0
    for k in range(steps):
        for _ in range(4):
            q, qd = d.qpos[qadr], d.qvel[dadr]
            d.ctrl[aid] = clip_torque_speed(KP * (target - q) - KD * qd, qd)
            mujoco.mj_step(m, d)
        obs[0:3] = d.qvel[bd + 3:bd + 6] * 0.25
        obs[3:6] = gravity(d.qpos[bq + 3:bq + 7])
        obs[6:9] = CMD
        obs[9:21] = d.qpos[qadr] - DEFAULT
        obs[21:33] = d.qvel[dadr] * 0.05
        obs[33:45] = action
        with torch.inference_mode():
            mu, _ = net(torch.as_tensor(obs, dtype=torch.float32, device=dev).unsqueeze(0))
        action = mu.cpu().numpy()[0]
        target = DEFAULT + 0.25 * action
        vxs.append(float(d.qvel[bd]))
        up_now = float(d.xmat[bb].reshape(3, 3)[2, 2])
        if shots and float(d.time) >= shots[0]:
            t = shots.pop(0)
            cam.lookat[:] = [float(d.qpos[bq]), float(d.qpos[bq + 1]), float(d.qpos[bq + 2])]
            renderer.update_scene(d, camera=cam)
            save_rgb(renderer.render(), "shots/village_t%04.1f.png" % t)
        if up_now < 0.5:
            print("  第 %d 步（%.1f 秒）倾倒" % (k, k * 0.02))
            break
    dist = float(np.hypot(d.qpos[bq] - x0, d.qpos[bq + 1] - y0))
    print("村子行走：位移 %.2f m | 平均 vx %.2f m/s | 时长 %.1f s | 机身倾角 cos %.2f"
          % (dist, float(np.mean(vxs)), len(vxs) * 0.02, up_now))


if __name__ == "__main__":
    main()
