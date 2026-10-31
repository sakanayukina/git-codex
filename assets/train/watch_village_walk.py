"""在交互窗口里看 Go2 在村子地形上走（真实物理 + 策略闭环）。

    python watch_village_walk.py                        # 默认 village_walk_final.xml（含 610 碰撞代理）
    python watch_village_walk.py --at 0 -20 --cmd 1.0   # 换位置 / 换速度指令
    python watch_village_walk.py --headless --seconds 5 # 不开窗口，只报数字

跟 run_scene.py 的区别：run_scene 只是"被动播放物理"（demo_v32 里的机器人还是焊死基座的），
这里每 0.02 s 跑一次策略并把力矩写进执行器，所以机器人会真的走。
"""
import argparse
import os
import time

import mujoco

import terrain_road
import numpy as np
import torch

from ppo import ActorCritic
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity

JOINTS = ["FL_hip", "FL_thigh", "FL_calf", "FR_hip", "FR_thigh", "FR_calf",
          "RL_hip", "RL_thigh", "RL_calf", "RR_hip", "RR_thigh", "RR_calf"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=os.path.join("..", "village_walk_final.xml"))
    ap.add_argument("--ckpt", default="ckpt/bc.pt")
    ap.add_argument("--at", nargs=2, type=float, default=[12.0, -18.0])
    ap.add_argument("--cmd", type=float, default=1.0, help="obs 里的速度指令（1.0 ≈ 0.5 m/s）")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--follow", action="store_true", help="相机跟随机器人")
    ap.add_argument("--noprop", action="store_true", help="关掉村子道具/植被的碰撞（只留地形与建筑）")
    a = ap.parse_args()

    m = terrain_road.load_model(a.xml)
    m.opt.timestep = 0.005
    m.opt.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    m.opt.cone = mujoco.mjtCone.mjCONE_PYRAMIDAL
    m.opt.impratio = 1.0
    if a.noprop:
        hf0 = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
        bb0 = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
        kids = {}
        for i in range(m.nbody):
            kids.setdefault(int(m.body_parentid[i]), []).append(i)
        robot0, stack = set(), [bb0]
        while stack:
            b = stack.pop(); robot0.add(b); stack.extend(kids.get(b, []))
        n_off = 0
        for g in range(m.ngeom):
            if g == hf0 or int(m.geom_bodyid[g]) in robot0:
                continue
            m.geom_contype[g] = 0
            m.geom_conaffinity[g] = 0
            n_off += 1
        print("关掉 %d 个非机器人几何的碰撞" % n_off)
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
    d.qpos[bq:bq + 3] = [a.at[0] + 500.0, a.at[1] + 500.0, -800.0]
    mujoco.mj_forward(m, d)
    gz = None
    for dx, dy in [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2)]:
        dist = mujoco.mj_ray(m, d, np.array([a.at[0] + dx, a.at[1] + dy, 300.0]),
                             np.array([0.0, 0.0, -1.0]), grp, 1, -1, gid)
        if dist > 0 and int(gid[0]) == hf:
            gz = 300.0 - dist
            break
    gz = 5.0 if gz is None else gz
    d.qpos[bq:bq + 3] = [a.at[0], a.at[1], gz + 0.45]
    d.qpos[bq + 3:bq + 7] = [1, 0, 0, 0]
    d.qpos[qadr] = DEFAULT
    mujoco.mj_forward(m, d)
    print("地面 %.2f m，起点 (%.1f, %.1f)" % (gz, a.at[0], a.at[1]))

    net = ActorCritic()
    net.load_state_dict(torch.load(a.ckpt, map_location="cpu")["net"])
    net.eval()

    obs = np.zeros(45, dtype=np.float32)
    action = np.zeros(12, dtype=np.float32)
    target = DEFAULT.copy()
    x0, y0 = float(d.qpos[bq]), float(d.qpos[bq + 1])
    n_steps = int(a.seconds / 0.02)

    def control_step():
        nonlocal obs, action, target
        for _ in range(4):
            q, qd = d.qpos[qadr], d.qvel[dadr]
            d.ctrl[aid] = clip_torque_speed(KP * (target - q) - KD * qd, qd)
            mujoco.mj_step(m, d)
        obs[0:3] = d.qvel[bd + 3:bd + 6] * 0.25
        obs[3:6] = gravity(d.qpos[bq + 3:bq + 7])
        obs[6:9] = [a.cmd, 0.0, 0.0]
        obs[9:21] = d.qpos[qadr] - DEFAULT
        obs[21:33] = d.qvel[dadr] * 0.05
        obs[33:45] = action
        with torch.inference_mode():
            mu, _ = net(torch.as_tensor(obs).unsqueeze(0))
        action = mu.numpy()[0]
        target = DEFAULT + 0.25 * action

    if a.headless:
        for _ in range(n_steps):
            control_step()
        dist = float(np.hypot(d.qpos[bq] - x0, d.qpos[bq + 1] - y0))
        print("headless：位移 %.2f m，末高 %.2f（地面 %.2f）" % (dist, d.qpos[bq + 2], gz))
        return

    with mujoco.viewer.launch_passive(m, d) as v:
        v.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        v.cam.distance = 6.0
        v.cam.azimuth = 135
        v.cam.elevation = -18
        v.cam.lookat[:] = [d.qpos[bq], d.qpos[bq + 1], d.qpos[bq + 2]]
        print("窗口已打开：按中键拖动/滚轮缩放；关窗口结束。")
        t_next = time.perf_counter()
        for k in range(n_steps * 20):          # 最多跑 20 倍时长
            if not v.is_running():
                break
            control_step()
            if a.follow:
                v.cam.lookat[:] = [d.qpos[bq], d.qpos[bq + 1], d.qpos[bq + 2]]
            v.sync()
            t_next += 0.02
            dt = t_next - time.perf_counter()
            if dt > 0:
                time.sleep(dt)
            else:
                t_next = time.perf_counter()
        dist = float(np.hypot(d.qpos[bq] - x0, d.qpos[bq + 1] - y0))
        print("结束：位移 %.2f m，末高 %.2f" % (dist, d.qpos[bq + 2]))


if __name__ == "__main__":
    main()
