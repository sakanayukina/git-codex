r"""在任意场景里用官方 motion.pt 驱动 G1（按关节名定位，不依赖 qpos 偏移）。

和 g1_policy.py 的区别：那个脚本假设"场景里只有一台 12 自由度 G1"，
用 qpos[7:19] 硬编码取关节；本脚本按名字找，因此可以跑在同时含 Go2、
瓦砾 free joint 的村子里。

    python scene_walk.py --xml ../demo_v32.xml --vx 0.5 --seconds 5
    python scene_walk.py --xml ../demo_v32.xml --viewer

前提：场景里的 G1 必须是 12 自由度版（12 个 motor，力矩控制），且带 freejoint。
"""
import argparse
import math
import os

import mujoco
import mujoco.viewer
import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)

JOINTS = [f"{s}_{j}_joint" for s in ("left", "right")
          for j in ("hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll")]
KP = [100, 100, 100, 150, 40, 40] * 2      # 与 yaml 顺序 (hip_pitch, hip_roll, hip_yaw, knee, ankle_pitch, ankle_roll) 对齐
KD = [2, 2, 2, 4, 2, 2] * 2
DEFAULT = [-0.1, 0.0, 0.0, 0.3, -0.2, 0.0] * 2
SCALE = dict(ang_vel=0.25, dof_pos=1.0, dof_vel=0.05, action=0.25)
CMD_SCALE = np.array([2.0, 2.0, 0.25])
NUM_ACT, NUM_OBS = 12, 47
PERIOD = 0.8


def gravity_orientation(q):
    qw, qx, qy, qz = q
    return np.array([2 * (-qz * qx + qw * qy), -2 * (qz * qy + qw * qx),
                     1 - 2 * (qw * qw + qz * qz)], dtype=np.float32)


def find_rig(m):
    """返回 (qpos 索引, qvel 索引, 执行器索引, 基座 qpos 起点, 基座 qvel 起点)。"""
    qadr, dadr, aid = [], [], []
    for jn in JOINTS:
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn)
        if j < 0:
            raise SystemExit(f"场景里没有关节 {jn}")
        qadr.append(int(m.jnt_qposadr[j]))
        dadr.append(int(m.jnt_dofadr[j]))
        # 找控制这个关节的执行器
        a = next((i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == j), -1)
        if a < 0:
            raise SystemExit(f"关节 {jn} 没有对应执行器")
        aid.append(a)
    # 基座自由关节：优先按名字，其次找 pelvis body 上的 free joint
    bj = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "floating_base_joint")
    if bj < 0 or m.jnt_type[bj] != mujoco.mjtJoint.mjJNT_FREE:
        pid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
        bj = -1
        for j in range(m.njnt):
            if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE and int(m.jnt_bodyid[j]) == pid:
                bj = j
                break
    if bj < 0:
        raise SystemExit("找不到 G1 的 free joint（是不是固定基座版？）")
    bq = int(m.jnt_qposadr[bj])
    bd = int(m.jnt_dofadr[bj])
    return qadr, dadr, aid, bq, bd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True)
    ap.add_argument("--policy", default=os.path.join(ASSETS, "props", "robots", "g1", "motion.pt"))
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--vx", type=float, default=0.5)
    ap.add_argument("--viewer", action="store_true")
    a = ap.parse_args()

    m = mujoco.MjModel.from_xml_path(a.xml)
    m.opt.timestep = 0.002
    d = mujoco.MjData(m)
    if m.nkey > 0:
        mujoco.mj_resetDataKeyframe(m, d, 0)
    qadr, dadr, aid, bq, bd = find_rig(m)

    # 把 G1 摆到默认姿态（只在开局做一次）
    for i, qa in enumerate(qadr):
        d.qpos[qa] = DEFAULT[i]
    mujoco.mj_forward(m, d)

    policy = torch.jit.load(a.policy)
    if hasattr(policy, "reset_memory"):
        policy.reset_memory()

    default = np.array(DEFAULT, dtype=np.float32)
    kp, kd = np.array(KP, dtype=np.float32), np.array(KD, dtype=np.float32)
    cmd = np.array([a.vx, 0.0, 0.0], dtype=np.float32)
    action = np.zeros(NUM_ACT, dtype=np.float32)
    target = default.copy()
    qa = np.array(qadr)
    da = np.array(dadr)
    aa = np.array(aid)

    def step(i):
        nonlocal action, target
        q = d.qpos[qa]
        dq = d.qvel[da]
        tau = kp * (target - q) - kd * dq
        d.ctrl[aa] = np.clip(tau, -200, 200)
        mujoco.mj_step(m, d)
        if i % 10 == 0:
            t = i * m.opt.timestep
            ph = (t % PERIOD) / PERIOD
            obs = np.zeros(NUM_OBS, dtype=np.float32)
            obs[0:3] = d.qvel[bd + 3:bd + 6] * SCALE["ang_vel"]
            obs[3:6] = gravity_orientation(d.qpos[bq + 3:bq + 7])
            obs[6:9] = cmd * CMD_SCALE
            obs[9:21] = (d.qpos[qa] - default) * SCALE["dof_pos"]
            obs[21:33] = d.qvel[da] * SCALE["dof_vel"]
            obs[33:45] = action
            obs[45:47] = [math.sin(2 * math.pi * ph), math.cos(2 * math.pi * ph)]
            with torch.no_grad():
                action = policy(torch.from_numpy(obs).unsqueeze(0)).numpy().flatten()[:NUM_ACT]
            target = default + SCALE["action"] * action

    p0 = np.array(d.qpos[bq:bq + 3], dtype=float)
    zs = []

    if a.viewer:
        i = 0
        with mujoco.viewer.launch_passive(m, d) as v:
            v.cam.lookat[:] = [p0[0], p0[1], p0[2] - 0.4]
            v.cam.distance, v.cam.elevation = 3.5, -12
            while v.is_running():
                step(i)
                i += 1
                v.cam.lookat[:] = [float(d.qpos[bq]), float(d.qpos[bq + 1]), float(d.qpos[bq + 2]) - 0.4]
                v.sync()
        return

    n = int(a.seconds / m.opt.timestep)
    for i in range(n):
        step(i)
        zs.append(float(d.qpos[bq + 2]))
    p1 = np.array(d.qpos[bq:bq + 3], dtype=float)
    print(f"vx={a.vx:+.2f} 跑 {a.seconds:.0f}s | 骨盆位移 {np.linalg.norm(p1[:2]-p0[:2]):.2f} m "
          f"| 骨盆 z {min(zs):.2f}~{max(zs):.2f}（末 {p1[2]:.2f}）")


if __name__ == "__main__":
    main()
