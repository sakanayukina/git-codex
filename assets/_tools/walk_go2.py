r"""Go2 开环 trot（对角步态）：12 个位置电机按相位摆动，让狗在 yard 上真的走起来。

    python walk_go2.py                        # 用默认参数跑 5 s，报指标
    python walk_go2.py --sweep                # 扫参数，挑走得最远的
    python walk_go2.py --render out.png       # 走 3 s 后出图

指标：
    dist  水平位移（m），越大越好
    yaw  航向漂移（rad），越小越直
    zmin  机身最低高度，<0.12 基本就是趴了
"""
import argparse
import itertools
import math
import os

import mujoco
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)

# Go2 关节顺序（go2_scene.xml 里的 actuator 名）
LEGS = {
    "FL": dict(thigh="FL_thigh_joint", calf="FL_calf_joint", phase=0.0),
    "RR": dict(thigh="RR_thigh_joint", calf="RR_calf_joint", phase=0.0),
    "FR": dict(thigh="FR_thigh_joint", calf="FR_calf_joint", phase=math.pi),
    "RL": dict(thigh="RL_thigh_joint", calf="RL_calf_joint", phase=math.pi),
}
# 爬行步态：四条腿错开 1/4 周期，任何时刻只有一条腿离地 → 静态稳定
CRAWL_PHASE = {"FL": 0.0, "RR": 0.25, "FR": 0.5, "RL": 0.75}


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


def make_controller(m, freq=2.0, a_thigh=0.22, a_calf=0.55, thigh0=0.95,
                    calf0=-1.55, gait="crawl"):
    """返回 (model, data, t) -> None 的控制器，方便在 viewer 里逐帧调用。"""
    ctrl_id = {}
    for leg in LEGS:
        ctrl_id[leg] = tuple(
            mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, f"{leg}_{j}_joint_pos")
            for j in ("hip", "thigh", "calf"))

    def step(model, data, t):
        ph = 2 * math.pi * freq * t
        for leg, c in LEGS.items():
            off = c["phase"] if gait == "trot" else 2 * math.pi * CRAWL_PHASE[leg]
            s = math.sin(ph + off)
            lift = max(0.0, s) ** (1 if gait == "trot" else 4)
            hi, ti, ci = ctrl_id[leg]
            data.ctrl[hi] = 0.0
            data.ctrl[ti] = thigh0 + a_thigh * s
            data.ctrl[ci] = calf0 - a_calf * lift

    return step


def run(xml, seconds=5.0, freq=2.2, a_thigh=0.35, a_calf=0.45,
        thigh0=0.85, calf0=-1.55, kp_extra=0.0, render=None, feedback=False, steer=0.0, gait="trot"):
    m = mujoco.MjModel.from_xml_path(xml)
    d = mujoco.MjData(m)
    if m.nkey > 0:
        mujoco.mj_resetDataKeyframe(m, d, 0)
    mujoco.mj_forward(m, d)

    bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
    ctrl_id = {}
    hip_id = {}
    for leg, c in LEGS.items():
        ctrl_id[leg] = (
            mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, leg + "_thigh_joint_pos"),
            mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, leg + "_calf_joint_pos"),
        )
        hip_id[leg] = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, leg + "_hip_joint_pos")
    if any(i < 0 for pair in ctrl_id.values() for i in pair):
        raise SystemExit("找不到 Go2 的 thigh/calf 电机")

    p0 = np.array(d.xpos[bid][:2], dtype=float)
    q0 = d.xquat[bid]
    yaw0 = math.atan2(2 * (q0[0] * q0[3] + q0[1] * q0[2]), 1 - 2 * (q0[2] ** 2 + q0[3] ** 2))
    zs = []
    dt = m.opt.timestep
    n = int(seconds / dt)

    LEFT = ("FL", "RL")                      # 左侧两条腿（转向靠左右步幅差）
    for i in range(n):
        t = i * dt
        ph = 2 * math.pi * freq * t
        gain_l = gain_r = 1.0
        pitch_fix = 0.0
        err_yaw_s = 0.0
        if feedback or steer != 0.0:
            q = d.xquat[bid]
            yaw_now = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]),
                                 1 - 2 * (q[2] ** 2 + q[3] ** 2))
            err_yaw = math.atan2(math.sin(yaw0 - yaw_now), math.cos(yaw0 - yaw_now))
            k = max(-0.5, min(0.5, 0.9 * err_yaw))
            err_yaw_s = err_yaw
            gain_l, gain_r = 1.0 + k, 1.0 - k
            # 机身俯仰：抬头就减小前腿摆幅，低头反之（简单反射，抑止前翻）
            r, p = d.xquat[bid][1], d.xquat[bid][2]
            pitch = math.asin(max(-1.0, min(1.0, 2 * (q[0] * q[1] - q[2] * q[3]))))
            pitch_fix = max(-0.25, min(0.25, 1.2 * pitch))
        for leg, c in LEGS.items():
            off = c["phase"] if gait == "trot" else 2 * math.pi * CRAWL_PHASE[leg]
            s = math.sin(ph + off)
            lift = max(0.0, s) ** (1 if gait == "trot" else 4)   # 爬行时把抬腿窗口压窄
            g = gain_l if leg in LEFT else gain_r
            thigh = thigh0 + a_thigh * g * s + pitch_fix
            calf = calf0 - a_calf * lift
            ti, ci = ctrl_id[leg]
            d.ctrl[ti] = thigh
            d.ctrl[ci] = calf
            if steer != 0.0 and hip_id[leg] >= 0:
                # 转向：髋外展差动（左右腿镜像，符号相反）
                d.ctrl[hip_id[leg]] = steer * err_yaw_s * (1 if leg in LEFT else -1)
        mujoco.mj_step(m, d)
        zs.append(float(d.xpos[bid][2]))

    p1 = np.array(d.xpos[bid][:2], dtype=float)
    quat = d.xquat[bid]
    yaw = math.atan2(2 * (quat[0] * quat[3] + quat[1] * quat[2]),
                     1 - 2 * (quat[2] ** 2 + quat[3] ** 2))
    res = dict(dist=float(np.linalg.norm(p1 - p0)),
               yaw=abs(yaw - yaw0) % (2 * math.pi),
               zmin=min(zs), zmax=max(zs), zend=zs[-1])

    if render:
        r = mujoco.Renderer(m, 600, 900)
        cam = mujoco.MjvCamera()
        mujoco.mjv_defaultFreeCamera(m, cam)
        cam.lookat[:] = [float(d.xpos[bid][0]), float(d.xpos[bid][1]), 0.3]
        cam.distance, cam.azimuth, cam.elevation = 3.2, 135, -18
        mujoco.mj_forward(m, d)
        r.update_scene(d, camera=cam)
        save_png(r.render(), render)
        r.close()
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=os.path.join(ASSETS, "yard_flat.xml"))
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--freq", type=float, default=2.2)
    ap.add_argument("--a-thigh", type=float, default=0.35)
    ap.add_argument("--a-calf", type=float, default=0.45)
    ap.add_argument("--thigh0", type=float, default=0.85)
    ap.add_argument("--calf0", type=float, default=-1.55)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--render")
    a = ap.parse_args()

    if a.sweep:
        best = None
        grid = itertools.product([2.0, 2.6, 3.2], [0.25, 0.40, 0.55], [0.3, 0.5, 0.7])
        for f, at, ac in grid:
            r = run(a.xml, a.seconds, f, at, ac)
            ok = r["zmin"] > 0.12 and r["yaw"] < 0.6
            score = r["dist"] if ok else -1
            print(f"  f={f:.1f} thigh={at:.2f} calf={ac:.2f}  dist={r['dist']:.2f} "
                  f"yaw={r['yaw']:.2f} zmin={r['zmin']:.2f} {'OK' if ok else '失败'}")
            if score > (best[0] if best else 0):
                best = (score, f, at, ac, r)
        if best:
            print(f"\n最佳: freq={best[1]} a_thigh={best[2]} a_calf={best[3]} "
                  f"dist={best[4]['dist']:.2f} m  yaw={best[4]['yaw']:.2f} rad")
        return

    r = run(a.xml, a.seconds, a.freq, a.a_thigh, a.a_calf, a.thigh0, a.calf0,
            render=a.render)
    print(f"走了 {r['dist']:.2f} m | 航向漂移 {r['yaw']:.2f} rad | "
          f"机身 z {r['zmin']:.2f}~{r['zmax']:.2f}（末 {r['zend']:.2f}）")


if __name__ == "__main__":
    main()
