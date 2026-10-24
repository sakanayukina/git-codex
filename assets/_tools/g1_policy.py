r"""用宇树官方 G1 预训练策略（motion.pt，12 自由度腿版）驱动机器人。

    python g1_policy.py                        # 平地走 5 s（vx=0.5）
    python g1_policy.py --vx 0 --seconds 4     # 原地站
    python g1_policy.py --xml ../yard_flat.xml
    python g1_policy.py --render out.png

接口完全按 `deploy/deploy_mujoco/configs/g1.yaml` + `deploy_mujoco.py`：
    obs[0:3]   = ω * 0.25
    obs[3:6]   = 投影重力
    obs[6:9]   = cmd * [2, 2, 0.25]
    obs[9:21]  = (q - q_default)
    obs[21:33] = dq * 0.05
    obs[33:45] = 上一步 action
    obs[45:47] = [sin, cos](2πφ)，φ 周期 0.8 s
    控制 50 Hz（dt 0.002 × decimation 10），力矩 tau = kp(target−q) − kd·dq
"""
import argparse
import math
import os

import mujoco
import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)

KP = [100, 100, 100, 150, 40, 40, 100, 100, 100, 150, 40, 40]
KD = [2, 2, 2, 4, 2, 2, 2, 2, 2, 4, 2, 2]
DEFAULT = [-0.1, 0.0, 0.0, 0.3, -0.2, 0.0,
           -0.1, 0.0, 0.0, 0.3, -0.2, 0.0]
SCALE = dict(ang_vel=0.25, dof_pos=1.0, dof_vel=0.05, action=0.25)
CMD_SCALE = np.array([2.0, 2.0, 0.25])
NUM_ACT, NUM_OBS = 12, 47
PERIOD = 0.8


def gravity_orientation(q):
    qw, qx, qy, qz = q
    return np.array([
        2 * (-qz * qx + qw * qy),
        -2 * (qz * qy + qw * qx),
        1 - 2 * (qw * qw + qz * qz),
    ], dtype=np.float32)


def save_png(arr, path):
    import struct
    import zlib
    h, w = arr.shape[:2]
    raw = b"".join(b"\x00" + arr[y, :, :3].astype(np.uint8).tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    blob = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    blob += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    open(path, "wb").write(blob)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=os.path.join(ASSETS, "props", "robots", "g1",
                                                  "g1_12dof_scene.xml"))
    ap.add_argument("--policy", default=os.path.join(ASSETS, "props", "robots", "g1", "motion.pt"))
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--vx", type=float, default=0.5)
    ap.add_argument("--render")
    ap.add_argument("--swap-roll-yaw", action="store_true",
                    help="若策略的关节顺序是 (pitch, yaw, roll)，用它换回来")
    a = ap.parse_args()

    m = mujoco.MjModel.from_xml_path(a.xml)
    m.opt.timestep = 0.002
    d = mujoco.MjData(m)
    if m.nkey > 0:
        mujoco.mj_resetDataKeyframe(m, d, 0)
    d.qpos[0:3] = [0.0, 0.0, 0.8]
    d.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    d.qpos[7:19] = DEFAULT
    mujoco.mj_forward(m, d)
    if m.nq != 19 or m.nu != 12:
        raise SystemExit(f"模型不对：nq={m.nq} nu={m.nu}（要 19 / 12）")

    policy = torch.jit.load(a.policy)
    if hasattr(policy, "reset_memory"):
        policy.reset_memory()

    default = np.array(DEFAULT, dtype=np.float32)
    kp = np.array(KP, dtype=np.float32)
    kd = np.array(KD, dtype=np.float32)
    cmd = np.array([a.vx, 0.0, 0.0], dtype=np.float32)
    action = np.zeros(NUM_ACT, dtype=np.float32)
    target = default.copy()
    # 每侧 [hip_pitch, hip_roll, hip_yaw, knee, ankle_pitch, ankle_roll]
    perm = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
    if a.swap_roll_yaw:
        perm = np.array([0, 2, 1, 3, 4, 5, 6, 8, 7, 9, 10, 11])
    inv = np.argsort(perm)

    decim = 10
    steps = int(a.seconds / m.opt.timestep)
    zs, xs = [], []
    bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "pelvis")

    with torch.no_grad():
        for i in range(steps):
            q = d.qpos[7:19]
            dq = d.qvel[6:18]
            tau = kp * (target - q) - kd * dq
            d.ctrl[:] = np.clip(tau, -200, 200)
            mujoco.mj_step(m, d)
            if i % decim == 0:
                t = i * m.opt.timestep
                ph = (t % PERIOD) / PERIOD
                obs = np.zeros(NUM_OBS, dtype=np.float32)
                obs[0:3] = d.qvel[3:6] * SCALE["ang_vel"]
                obs[3:6] = gravity_orientation(d.qpos[3:7])
                obs[6:9] = cmd * CMD_SCALE
                obs[9:21] = (d.qpos[7:19] - default)[perm] * SCALE["dof_pos"]
                obs[21:33] = d.qvel[6:18][perm] * SCALE["dof_vel"]
                obs[33:45] = action
                obs[45:47] = [math.sin(2 * math.pi * ph), math.cos(2 * math.pi * ph)]
                action = policy(torch.from_numpy(obs).unsqueeze(0)).numpy().flatten()[:NUM_ACT]
                target = default + SCALE["action"] * action[inv]
            if i % 100 == 0:
                zs.append(float(d.xpos[bid][2]))
                xs.append(float(d.xpos[bid][0]))

    yaw_q = d.qpos[3:7]
    yaw = math.atan2(2 * (yaw_q[0] * yaw_q[3] + yaw_q[1] * yaw_q[2]),
                     1 - 2 * (yaw_q[2] ** 2 + yaw_q[3] ** 2))
    print(f"cmd vx={a.vx:+.2f} 跑 {a.seconds:.0f} s | 位移 x={d.xpos[bid][0]:+.2f} m "
          f"| 骨盆 z {min(zs):.2f}~{max(zs):.2f}（末 {d.xpos[bid][2]:.2f}）| 航向 {yaw:+.2f} rad")

    if a.render:
        r = mujoco.Renderer(m, 640, 900)
        cam = mujoco.MjvCamera()
        mujoco.mjv_defaultFreeCamera(m, cam)
        cam.lookat[:] = [float(d.xpos[bid][0]), 0.0, 0.5]
        cam.distance, cam.azimuth, cam.elevation = 2.8, 135, -12
        mujoco.mj_forward(m, d)
        r.update_scene(d, camera=cam)
        save_png(r.render(), a.render)
        r.close()


if __name__ == "__main__":
    main()
