r"""Go2 三自由度 IK 步态：足端轨迹 + 逆解，能走直线也能转。

    python trot_ik.py                    # 走 6 s，报里程/航向
    python trot_ik.py --vel 0.6          # 指定前进速度
    python trot_ik.py --render out.png

和 walk_go2.py（开环正弦）的区别：这里足端落点在世界坐标里算，
每步都重新做 IK，所以不会因为相位误差积累而绕圈。
"""
import argparse
import math
import os

import mujoco
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)

L1 = L2 = 0.213                       # 大腿 / 小腿长度（unitree_ros go2）
# 每条腿：髋在机身坐标里的偏移 + 步态相位
LEGS = {
    "FL": dict(x=+0.1934, y=+0.0465, ph=0.0),
    "RR": dict(x=-0.1934, y=-0.0465, ph=0.0),
    "FR": dict(x=+0.1934, y=-0.0465, ph=math.pi),
    "RL": dict(x=-0.1934, y=+0.0465, ph=math.pi),
}


def ik_leg(vx, vy, vz, side):
    """足端相对髋关节的向量 → (hip, thigh, calf) 关节角。"""
    d = math.sqrt(vx * vx + vy * vy + vz * vz)
    d = min(max(d, 1e-4), L1 + L2 - 1e-4)
    q3 = math.acos(max(-1.0, min(1.0, (d * d - L1 * L1 - L2 * L2) / (2 * L1 * L2))))
    q1 = math.atan2(vy, -vz)
    lz = -math.sqrt(max(1e-9, vy * vy + vz * vz))
    q2 = math.atan2(vx, -lz) - math.atan2(L2 * math.sin(q3), L1 + L2 * math.cos(q3))
    return q1 * side, q2, -q3          # calf 负号：膝向后弯


def foot_pos(model, data, leg):
    """FK：足端在机身坐标里的位置（用 calf 末端 body 推算，脚球半径 0.022）。"""
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"{leg}_calf")
    base = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "base")
    p = data.xpos[bid] - data.xpos[base]
    # calf body 的 z 就是脚踝，脚底再往下 0.022
    return np.array([p[0], p[1], p[2] - 0.022])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=os.path.join(ASSETS, "yard_flat.xml"))
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--vel", type=float, default=0.5)
    ap.add_argument("--yaw-rate", type=float, default=0.0)
    ap.add_argument("--freq", type=float, default=2.5)
    ap.add_argument("--height", type=float, default=0.29)
    ap.add_argument("--stride", type=float, default=0.10)
    ap.add_argument("--lift", type=float, default=0.07)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--render")
    a = ap.parse_args()

    m = mujoco.MjModel.from_xml_path(a.xml)
    d = mujoco.MjData(m)
    if m.nkey > 0:
        mujoco.mj_resetDataKeyframe(m, d, 0)
    mujoco.mj_forward(m, d)
    bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")

    if a.selftest:
        # 用 home 姿态的足端位置反解，应该返回 home 的关节角
        for leg in LEGS:
            f = foot_pos(m, d, leg)
            q1, q2, q3 = ik_leg(f[0] - LEGS[leg]["x"], f[1] - LEGS[leg]["y"], f[2], 1)
            jt = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f"{leg}_thigh_joint")
            jc = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f"{leg}_calf_joint")
            print(f"  {leg}: 目标足端 {np.round(f,3)} → IK thigh={q2:+.3f} calf={q3:+.3f} | "
                  f"实际 thigh={d.qpos[m.jnt_qposadr[jt]]:+.3f} calf={d.qpos[m.jnt_qposadr[jc]]:+.3f}")
        return

    act = {}
    for leg in LEGS:
        act[leg] = tuple(mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, f"{leg}_{j}_joint_pos")
                         for j in ("hip", "thigh", "calf"))
        if min(act[leg]) < 0:
            raise SystemExit(f"找不到 {leg} 的电机")

    T = 1.0 / a.freq
    dt = m.opt.timestep
    p0 = np.array(d.xpos[bid][:2], dtype=float)
    q0 = d.xquat[bid]
    yaw0 = math.atan2(2 * (q0[0] * q0[3] + q0[1] * q0[2]), 1 - 2 * (q0[2] ** 2 + q0[3] ** 2))
    zs = []

    for i in range(int(a.seconds / dt)):
        t = i * dt
        # 机身当前位姿 → 世界到机身的旋转
        q = d.xquat[bid]
        yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
        c, s = math.cos(yaw), math.sin(yaw)
        for leg, cfg in LEGS.items():
            u = ((t / T) + cfg["ph"] / (2 * math.pi)) % 1.0
            # 落点：以髋正下方为基准，沿行进方向偏移半个支撑相
            fx = cfg["x"] + (a.vel * T * 0.25 if u < 0.5 else -a.vel * T * 0.25)
            fy = cfg["y"]
            fz = -(a.height - 0.0)
            if u >= 0.5:                       # 摆动相：抬脚并前送
                w = (u - 0.5) * 2.0
                fz += a.lift * math.sin(math.pi * w)
                fx += a.stride * (w - 0.5)
            vx, vy, vz = fx - cfg["x"], fy - cfg["y"], fz
            # 转向：把落点绕机身 z 轴转一点
            if a.yaw_rate:
                ang = a.yaw_rate * T * 0.25 * (1 if u < 0.5 else -1)
                vx, vy = (vx * math.cos(ang) - vy * math.sin(ang),
                          vx * math.sin(ang) + vy * math.cos(ang))
            q1, q2, q3 = ik_leg(vx, vy, vz, 1)
            hi, ti, ci = act[leg]
            d.ctrl[hi], d.ctrl[ti], d.ctrl[ci] = q1, q2, q3
        mujoco.mj_step(m, d)
        zs.append(float(d.xpos[bid][2]))

    p1 = np.array(d.xpos[bid][:2], dtype=float)
    q = d.xquat[bid]
    yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
    disp = p1 - p0
    moved = float(np.linalg.norm(disp))
    print(f"位移 {moved:.2f} m（目标方向分量 {disp[0] * c + disp[1] * s:+.2f}）| "
          f"航向漂移 {abs(yaw - yaw0):.2f} rad | 机身 z {min(zs):.2f}~{max(zs):.2f}")

    if a.render:
        r = mujoco.Renderer(m, 600, 900)
        cam = mujoco.MjvCamera()
        mujoco.mjv_defaultFreeCamera(m, cam)
        cam.lookat[:] = [float(d.xpos[bid][0]), float(d.xpos[bid][1]), 0.3]
        cam.distance, cam.azimuth, cam.elevation = 3.0, 135, -15
        mujoco.mj_forward(m, d)
        r.update_scene(d, camera=cam)
        from walk_go2 import save_png
        save_png(r.render(), a.render)
        r.close()


if __name__ == "__main__":
    main()
