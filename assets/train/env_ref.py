"""用 run_ref 的循环逻辑包装成训练环境接口（保证与已验证运行器逐位一致）。

    python env_ref.py --demo 5     # 用开源策略跑 5 秒，验证环境
"""
import argparse
import math
import os

import mujoco
import numpy as np

import env as E
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity

SIM_DT, DECIM = 0.005, 4
ACTION_SCALE = 0.25
EPISODE_STEPS = 500
CMD = np.array([1.0, 0.0, 0.0], dtype=np.float32)   # obs 里的速度指令（=cmd×2）
OBS_DIM, ACT_DIM = 45, 12


class Go2EnvRef:
    def __init__(self, seed=0, terrain_h=0.1, half=40.0):
        E.SIM_DT, E.DECIM = SIM_DT, DECIM
        os.environ.setdefault("DSH_MODEL", "author")
        os.environ.setdefault("DSH_GROUND", "plane")
        png = os.environ.get("DSH_TERRAIN_PNG") or os.path.join(E.TMP, "dem80_128.png")
        self.m = mujoco.MjModel.from_xml_string(E.make_xml(png, half, terrain_h))
        self.d = mujoco.MjData(self.m)
        self.rng = np.random.default_rng(seed + 7)
        self.half = half
        self.qadr, self.dadr, self.aid = [], [], []
        for jn in E.JOINTS:
            j = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_JOINT, jn + "_joint")
            self.qadr.append(int(self.m.jnt_qposadr[j]))
            self.dadr.append(int(self.m.jnt_dofadr[j]))
            self.aid.append(next(i for i in range(self.m.nu)
                                 if int(self.m.actuator_trnid[i][0]) == j))
        self.qadr = np.array(self.qadr); self.dadr = np.array(self.dadr)
        self.aid = np.array(self.aid)
        self.target = DEFAULT.copy()
        self.prev_action = np.zeros(ACT_DIM, dtype=np.float32)
        self.steps = 0
        self.reset()

    def _ground(self, x, y):
        gid = np.array([-1], dtype=np.int32)
        grp = np.array([0, 1, 0, 0, 0, 0], dtype=np.uint8)
        dist = mujoco.mj_ray(self.m, self.d, np.array([x, y, 500.0]),
                             np.array([0.0, 0.0, -1.0]), grp, 1, -1, gid)
        return float(500.0 - dist) if dist > 0 else 0.0

    def reset(self):
        d, m = self.d, self.m
        mujoco.mj_resetData(m, d)
        x = self.rng.uniform(-self.half * 0.5, self.half * 0.5)
        y = self.rng.uniform(-self.half * 0.5, self.half * 0.5)
        d.qpos[0:3] = [x, y, 60.0]
        mujoco.mj_forward(m, d)
        gz = self._ground(x, y)
        d.qpos[0:3] = [x, y, gz + 0.45]
        d.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
        d.qpos[self.qadr] = DEFAULT
        mujoco.mj_forward(m, d)
        self.target = DEFAULT.copy()
        self.prev_action[:] = 0.0
        self.steps = 0
        return self._obs()

    def _obs(self):
        d = self.d
        o = np.zeros(OBS_DIM, dtype=np.float32)
        o[0:3] = d.qvel[3:6] * 0.25
        o[3:6] = gravity(d.qpos[3:7])
        o[6:9] = CMD
        o[9:21] = d.qpos[self.qadr] - DEFAULT
        o[21:33] = d.qvel[self.dadr] * 0.05
        o[33:45] = self.prev_action
        return o

    def step(self, action):
        action = np.clip(np.asarray(action, dtype=np.float32), -100.0, 100.0)
        self.target = DEFAULT + ACTION_SCALE * action
        d = self.d
        for _ in range(DECIM):                      # 与 run_ref 完全相同的内层循环
            q, qd = d.qpos[self.qadr], d.qvel[self.dadr]
            d.ctrl[self.aid] = clip_torque_speed(KP * (self.target - q) - KD * qd, qd)
            mujoco.mj_step(self.m, d)
        self.prev_action = action.copy()
        self.steps += 1

        z = float(d.qpos[2])
        gz = self._ground(float(d.qpos[0]), float(d.qpos[1]))
        dz = z - gz
        up = float(d.xmat[1].reshape(3, 3)[2, 2])
        v = d.qvel[0:3]
        # 线性速度跟踪：站着不动 = 0 分，走到 0.5 m/s = 4 分（拉开差距，破除"站着"局部最优）
        r = 4.0 * float(np.clip(1.0 - abs(v[0] - 0.5) / 0.5, -1.0, 1.0))
        r += 0.3 * up + 0.4 * math.exp(-((dz - 0.32) ** 2) / 0.01)
        r -= 0.02 * float(np.abs(d.qvel[self.dadr]).sum())
        fell = up < 0.6 or dz < 0.14
        if fell:
            r -= 5.0
        done = fell or self.steps >= EPISODE_STEPS
        return self._obs(), float(r), done, {"fell": fell, "z": dz, "vx": float(v[0])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", type=float, default=5.0)
    a = ap.parse_args()
    import torch
    env = Go2EnvRef(seed=0, terrain_h=0.1)
    env.real = True
    env.reset()
    env.d.qpos[0:3] = [0.0, 0.0, 0.45]
    mujoco.mj_forward(env.m, env.d)
    pol = torch.jit.load("pretrained/go2_cts_vanilla2_103.5k_0.5786.pt")
    pol.eval(); pol.reset()
    obs = env._obs()
    n = int(a.demo / (SIM_DT * DECIM))
    vxs = []
    for k in range(n):
        with torch.inference_mode():
            out = pol(torch.as_tensor(obs).unsqueeze(0))
        act = (out[0] if isinstance(out, tuple) else out).numpy().flatten()[:12]
        obs, r, done, info = env.step(act)
        vxs.append(info["vx"])
        if done:
            print("第 %d 步结束（%.2f 秒）fell=%s" % (k, k * 0.02, info["fell"]))
            break
    print("env_ref：位移 %.2f m | 平均 vx %.2f | 时长 %.2f s | 末 dz %.2f"
          % (env.d.qpos[0], float(np.mean(vxs)), len(vxs) * 0.02, info["z"]))


if __name__ == "__main__":
    main()


class VecEnvRef:
    """与 env.VecEnv 同接口，内部用 Go2EnvRef（已验证循环）。"""

    def __init__(self, n=16, terrain_h=0.1, half=40.0):
        self.envs = [Go2EnvRef(seed=i, terrain_h=terrain_h, half=half) for i in range(n)]
        self.n = n

    def reset(self):
        return np.stack([e.reset() for e in self.envs])

    def step(self, actions):
        obs, rew, done, infos = [], [], [], []
        for e, a in zip(self.envs, np.asarray(actions, dtype=np.float32)):
            o, r, dn, info = e.step(a)
            if dn:
                o = e.reset()
            obs.append(o); rew.append(r); done.append(dn); infos.append(info)
        return (np.stack(obs), np.array(rew, dtype=np.float32),
                np.array(done), infos)
