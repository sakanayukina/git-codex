"""Go2 粗糙地形训练环境（MuJoCo 并行，纯 numpy）。

    python env.py --bench     # 测吞吐
    python env.py --demo 3    # 冒烟测试
"""
import argparse
import math
import os
import re
import struct
import time
import zlib

import mujoco
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
GO2_SCENE = os.path.join(ASSETS, "props", "robots", "go2_urdf", "go2_scene.xml")
TMP = os.path.join(HERE, "_terrain")

JOINTS = ["FL_hip", "FL_thigh", "FL_calf",
          "FR_hip", "FR_thigh", "FR_calf",
          "RL_hip", "RL_thigh", "RL_calf",
          "RR_hip", "RR_thigh", "RR_calf"]
DEFAULT = np.array([0.0, 0.9, -1.8] * 4, dtype=np.float32)
KP = np.array([20.0, 20.0, 40.0] * 4)
KD = np.array([1.0, 1.0, 2.0] * 4)
ACTION_SCALE = 0.25
SIM_DT = 0.004
DECIM = 5
EPISODE_STEPS = 500
CMD = np.array([0.5, 0.0, 0.0], dtype=np.float32)
OBS_DIM = 45
ACT_DIM = 12

MOTOR = dict(X1=13.5, X2=30.0, Y1=20.2, Y2=23.4)     # Go2HV 转速-力矩包络
NUL = bytes([0])


def clip_torque_speed(effort, qd):
    same = qd * effort > 0.0
    max_e = np.where(same, MOTOR["Y1"], MOTOR["Y2"])
    high = max_e * (1.0 - (np.abs(qd) - MOTOR["X1"]) / (MOTOR["X2"] - MOTOR["X1"]))
    max_e = np.where(np.abs(qd) < MOTOR["X1"], max_e, np.maximum(high, 0.0))
    return np.clip(effort, -max_e, max_e)


def save_gray_png(arr, path):
    h, w = arr.shape
    rows = [NUL + arr[y].astype(np.uint8).tobytes() for y in range(h)]
    raw = b"".join(rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    blob = (header
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))
    open(path, "wb").write(blob)


def terrain_png(path, height, size=96, seed=0):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size] / size
    h = np.zeros((size, size), dtype=np.float64)
    for k in range(1, 5):
        fx, fy = rng.uniform(0.6, 2.5, 2) * k
        ph = rng.uniform(0, 2 * math.pi)
        h += np.sin(2 * math.pi * (fx * x + fy * y) + ph) / k
    h -= h.min()
    h /= max(h.max(), 1e-9)
    if rng.random() < 0.5:
        step = rng.integers(3, 10) / size
        h = np.maximum(h, (x > step) * 1.0)
    img = np.clip(h * 255, 0, 255).astype(np.uint8)   # 用满量程，真实起伏 = hfield z 尺寸
    save_gray_png(img, path)
    return path


def make_xml(png_abs, hfield_size=10.0, terrain_h=0.1):
    s = open(GO2_SCENE, encoding="utf-8").read()
    # go2_scene 的 <mesh file="meshes/x.obj"> 是相对它自己目录的；从字符串加载时
    # 找不到，改成绝对路径（MuJoCo 接受带盘符的路径）
    mesh_dir = os.path.join(ASSETS, "props", "robots", "go2_urdf").replace("\\", "/")
    s = re.sub(r'file="(meshes/[^"]+)"',
               lambda m: 'file="%s/%s"' % (mesh_dir, m.group(1)), s)
    s = re.sub(r"\s*<option[^>]*/>", "", s)
    s = s.replace("</mujoco>",
                  '  <option timestep="%g" integrator="implicitfast"/>\n</mujoco>' % SIM_DT, 1)
    s = re.sub(r'\s*<geom name="floor"[^>]*/>', "", s)
    s = s.replace("</asset>",
                  '<hfield name="terrain" file="%s" size="%g %g %g 0.01"/>\n  </asset>'
                  % (png_abs.replace("\\", "/"), hfield_size / 2, hfield_size / 2,
                     max(terrain_h, 0.01)), 1)
    s = s.replace("<worldbody>",
                  '<worldbody>\n    <geom name="ground" type="hfield" hfield="terrain" '
                  'friction="1.0 0.02 0.001"/>\n'
                  '    <light pos="0 0 3" dir="0 0 -1" directional="true"/>', 1)
    for j in range(12):
        nm = JOINTS[j] + "_joint_pos"
        s = re.sub(r'<position name="%s"[^>]*/>' % re.escape(nm),
                   '<motor name="%s" joint="%s_joint"/>' % (nm, JOINTS[j]), s)
    return s


class Go2Env:
    def __init__(self, seed=0, terrain_h=0.10, size=10.0):
        os.makedirs(TMP, exist_ok=True)
        png = os.path.join(TMP, "t_%02d_%03d.png" % (seed, int(terrain_h * 1000)))
        terrain_png(png, terrain_h, seed=seed)
        self.m = mujoco.MjModel.from_xml_string(make_xml(png, size, terrain_h))
        self.d = mujoco.MjData(self.m)
        self.bid = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_BODY, "base")
        self.aid = np.array([mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_ACTUATOR,
                                               j + "_joint_pos") for j in JOINTS])
        self.qadr = np.array([self.m.jnt_qposadr[
            mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_JOINT, j + "_joint")] for j in JOINTS])
        self.dadr = np.array([self.m.jnt_dofadr[
            mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_JOINT, j + "_joint")] for j in JOINTS])
        self.prev_action = np.zeros(ACT_DIM, dtype=np.float32)
        self.steps = 0
        self.reset()

    def reset(self):
        d, m = self.d, self.m
        mujoco.mj_resetData(m, d)
        d.qpos[0:3] = [0.0, 0.0, 0.34]
        d.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
        d.qpos[self.qadr] = DEFAULT
        mujoco.mj_forward(m, d)
        self.steps = 0
        self.prev_action[:] = 0.0
        return self._obs()

    def _obs(self):
        d = self.d
        # 用旋转矩阵算投影重力：g_body = R^T · (0,0,-1)
        R = d.xmat[self.bid].reshape(3, 3)
        grav = np.array([-R[0, 2], -R[1, 2], -R[2, 2]], dtype=np.float32)
        return np.concatenate([
            d.qvel[3:6].astype(np.float32),
            grav,
            CMD,
            (d.qpos[self.qadr] - DEFAULT).astype(np.float32),
            d.qvel[self.dadr].astype(np.float32) * 0.05,
            self.prev_action,
        ]).astype(np.float32)

    def _phase(self):
        t = self.steps * SIM_DT * DECIM
        ang = 2 * math.pi * t / PHASE_PERIOD
        return np.array([math.sin(ang), math.cos(ang)], dtype=np.float32)

    def step(self, action):
        action = np.clip(np.asarray(action, dtype=np.float32), -1, 1)
        target = DEFAULT + ACTION_SCALE * action
        for _ in range(DECIM):
            q = self.d.qpos[self.qadr]
            qd = self.d.qvel[self.dadr]
            eff = KP * (target - q) - KD * qd
            self.d.ctrl[self.aid] = clip_torque_speed(eff, qd)
            mujoco.mj_step(self.m, self.d)
        self.steps += 1
        self.prev_action = action

        z = float(self.d.qpos[2])
        v = self.d.qvel[0:3]
        up = float(self.d.xmat[self.bid].reshape(3, 3)[2, 2])   # cos(机身倾角)
        tau = float(np.abs(self.d.actuator_force[self.aid]).sum())

        # 速度跟踪用更窄的核 + 原地不动直接罚：否则"站着不动"是局部最优
        r = 2.5 * math.exp(-((v[0] - CMD[0]) ** 2) / 0.05)
        r += 0.3 * up
        r += 0.2 * math.exp(-((z - 0.30) ** 2) / 0.01)
        if self.steps > 20 and abs(v[0]) < 0.15:
            r -= 0.6
        r -= 0.0005 * tau
        r -= 0.02 * float(np.abs(self.d.qvel[self.dadr]).sum())
        fell = z < 0.16 or up < 0.6
        if fell:
            r -= 5.0
        done = fell or self.steps >= EPISODE_STEPS
        return self._obs(), float(r), done, {"fell": fell, "z": z, "vx": float(v[0])}


class VecEnv:
    def __init__(self, n=16, terrain_h=0.10):
        self.envs = [Go2Env(seed=i, terrain_h=terrain_h) for i in range(n)]
        self.n = n

    def reset(self):
        return np.stack([e.reset() for e in self.envs])

    def step(self, actions):
        obs, rew, done, infos = [], [], [], []
        for e, a in zip(self.envs, np.asarray(actions, dtype=np.float32)):
            o, r, dn, info = e.step(a)
            if dn:
                o = e.reset()
            obs.append(o)
            rew.append(r)
            done.append(dn)
            infos.append(info)
        return (np.stack(obs), np.array(rew, dtype=np.float32),
                np.array(done), infos)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", action="store_true")
    ap.add_argument("--demo", type=float, default=0.0)
    ap.add_argument("--n", type=int, default=16)
    a = ap.parse_args()

    if a.bench:
        venv = VecEnv(n=a.n)
        obs = venv.reset()
        print("环境 %d 个，obs dim = %s" % (a.n, obs.shape))
        t0 = time.time()
        steps = 200
        for _ in range(steps):
            venv.step(np.zeros((a.n, ACT_DIM), dtype=np.float32))
        dt = time.time() - t0
        print("%d 轮 x %d 环境 = %d env-step，%.1fs -> %.0f env-steps/s"
              % (steps, a.n, steps * a.n, dt, steps * a.n / dt))
        print("约 %.0f 物理步/s" % (steps * a.n * DECIM / dt))
        return

    env = Go2Env(seed=0, terrain_h=0.10)
    env.reset()
    n = int(a.demo / (SIM_DT * DECIM))
    tot = 0.0
    info = {}
    for i in range(n):
        o, r, done, info = env.step(np.zeros(ACT_DIM, dtype=np.float32))
        tot += r
        if done:
            print("  第 %d 步结束（fell=%s z=%.2f）" % (i, info["fell"], info["z"]))
            env.reset()
    print("空动作 %.1fs：累计奖励 %.1f，末态 z=%.2f vx=%.2f"
          % (a.demo, tot, info.get("z", 0), info.get("vx", 0)))


if __name__ == "__main__":
    main()
