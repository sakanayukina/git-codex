"""把训练好的策略（train/ckpt/bc.pt）放进村子场景，测它能走多远。

    python village_walk_test.py --xml ../village_walk_final.xml --seconds 10
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
    ap.add_argument("--xml", default="../village_walk_final.xml")
    ap.add_argument("--ckpt", default="ckpt/bc.pt")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--shots", default="")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--at", nargs=2, type=float, default=None, help="出生 x y")
    ap.add_argument("--village-physics", action="store_true", help="保留村子原始接触设置")
    ap.add_argument("--no-prop-collision", action="store_true",
                    help="关掉植被/碎石/道具的碰撞，只保留地形与建筑")
    a = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = ActorCritic().to(dev)
    net.load_state_dict(torch.load(a.ckpt, map_location=dev)["net"])
    net.eval()
    print("策略:", a.ckpt)

    m = mujoco.MjModel.from_xml_path(a.xml)
    if a.no_prop_collision:
        kw = ("tree", "grass", "rock", "debris", "seam", "stone", "trunk", "cone",
              "tire", "barrier", "car", "bush", "shrub", "wood", "plank")
        off = 0
        for g in range(m.ngeom):
            bn = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, int(m.geom_bodyid[g])) or ""
            gn = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
            low = (bn + " " + gn).lower()
            if any(k in low for k in kw):
                m.geom_contype[g] = 0
                m.geom_conaffinity[g] = 0
                off += 1
        print("  关掉 %d 个道具几何的碰撞" % off)
    m.opt.timestep = 0.005
    m.opt.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    # 与训练环境对齐接触/求解设置（村子场景默认是 elliptic cone + impratio 10）
    if not a.village_physics:
        m.opt.cone = mujoco.mjtCone.mjCONE_PYRAMIDAL
        m.opt.impratio = 1.0
        m.opt.solver = mujoco.mjtSolver.mjSOL_NEWTON
        m.opt.iterations = 100
        m.opt.ls_iterations = 50
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
    # 用射线取地形高度：只认 hfield geom（避免打到房顶/道具）
    hf = next(i for i in range(m.ngeom) if m.geom_type[i] == mujoco.mjtGeom.mjGEOM_HFIELD)
    d.qpos[bq:bq + 3] = [gx + 500.0, gy + 500.0, -800.0]
    mujoco.mj_forward(m, d)
    gid = np.array([-1], dtype=np.int32)
    grp = np.ones(6, dtype=np.uint8)

    def ground(x, y):
        for dx, dy in [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2), (4, 0), (-4, 0), (0, 4), (0, -4)]:
            dist = mujoco.mj_ray(m, d, np.array([x + dx, y + dy, 300.0]),
                                 np.array([0.0, 0.0, -1.0]), grp, 1, -1, gid)
            if dist > 0 and int(gid[0]) == hf:
                return 300.0 - dist
        return 5.0

    gz = ground(gx, gy)
    print("出生 (%.1f, %.1f) 地形高 %.2f" % (gx, gy, gz))
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
