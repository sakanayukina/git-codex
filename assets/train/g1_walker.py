r"""G1 行走控制器——把 `assets/_tools/g1_policy.py` 的内循环**逐行**搬成一个类。

存在的理由：`waypoint_nav.py` 自己重写的 G1 控制块在同一个场景、同一出生点、
同样指令下 1.0 s 就摔，而 `g1_policy.py` 同一位置能走 3.3 m。逐通道比对后发现差异只在
"什么时候算策略、什么时候写 ctrl"这类时序细节上，所以这里不再"等价重写"，而是照抄：

    for s in range(decim):
        写 ctrl（用上一拍的 target）
        mj_step
        if s == 0:            # 参考实现就是在每块的第一步之后更新策略
            算 obs → 策略 → target

对外只暴露 `step(vx, vyaw)`：执行一个 20 ms 控制块（decim=10 × dt 0.002）。

用法：
    from g1_walker import G1Walker
    w = G1Walker(m, d)
    for k in range(50):          # 1 s
        w.step(vx=0.5, vyaw=0.0)
"""

import math
import os

import mujoco
import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
DEFAULT_POLICY = os.path.join(ASSETS, "props", "robots", "g1", "motion.pt")

KP = np.array([100, 100, 100, 150, 40, 40, 100, 100, 100, 150, 40, 40], dtype=np.float64)
KD = np.array([2, 2, 2, 4, 2, 2, 2, 2, 2, 4, 2, 2], dtype=np.float64)
DEFAULT = np.array([-0.1, 0.0, 0.0, 0.3, -0.2, 0.0,
                    -0.1, 0.0, 0.0, 0.3, -0.2, 0.0], dtype=np.float64)
SCALE = dict(ang_vel=0.25, dof_pos=1.0, dof_vel=0.05, action=0.25)
CMD_SCALE = np.array([2.0, 2.0, 0.25], dtype=np.float64)
NUM_ACT, NUM_OBS = 12, 47
PERIOD = 0.8
DT = 0.002


def gravity_orientation(q):
    qw, qx, qy, qz = q
    return np.array([
        2 * (-qz * qx + qw * qy),
        -2 * (qz * qy + qw * qx),
        1 - 2 * (qw * qw + qz * qz),
    ], dtype=np.float32)


class G1Walker:
    """宇树官方 G1 12 自由度腿策略的行走控制器（与 g1_policy.py 时序一致）。"""

    def __init__(self, model, data, policy_path=None, decim=10, device="cpu"):
        if model.nq != 19 or model.nu != 12:
            raise SystemExit("G1 控制器需要 nq=19 / nu=12 的模型（当前 %d / %d）"
                             % (model.nq, model.nu))
        self.m = model
        self.d = data
        self.m.opt.timestep = DT
        self.decim = int(decim)
        self.policy = torch.jit.load(policy_path or DEFAULT_POLICY, map_location=device)
        self.policy.eval()
        if hasattr(self.policy, "reset_memory"):
            self.policy.reset_memory()
        self.default = DEFAULT.copy()
        self.action = np.zeros(NUM_ACT, dtype=np.float32)
        self.target = self.default.copy()
        self.steps = 0            # 物理步计数（相位靠它，必须连续）
        self.cmd = np.zeros(3, dtype=np.float64)
        # 每侧 [hip_pitch, hip_roll, hip_yaw, knee, ankle_pitch, ankle_roll]
        self.perm = np.arange(NUM_ACT)
        self.inv = np.argsort(self.perm)

    # ---- 状态 ----
    @property
    def q(self):
        return self.d.qpos[7:19]

    @property
    def dq(self):
        return self.d.qvel[6:18]

    def yaw(self):
        q = self.d.qpos[3:7]
        return math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))

    def pos(self):
        return np.array([self.d.qpos[0], self.d.qpos[1]])

    def up(self):
        bid = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
        return float(self.d.xmat[bid].reshape(3, 3)[2, 2])

    # ---- 控制 ----
    def _apply(self):
        tau = KP * (self.target - self.q) - KD * self.dq
        self.d.ctrl[:] = np.clip(tau, -200, 200)

    def _update_policy(self):
        # 参考实现在 i = 0, 10, 20… 处算策略，即相位对应"本块的第一步"。
        # self.steps 在 mj_step 之后自增，这里是第 1、11、21… 步之后，故减一。
        t = max(0, self.steps - 1) * self.m.opt.timestep
        ph = (t % PERIOD) / PERIOD
        obs = np.zeros(NUM_OBS, dtype=np.float32)
        obs[0:3] = self.d.qvel[3:6] * SCALE["ang_vel"]
        obs[3:6] = gravity_orientation(self.d.qpos[3:7])
        obs[6:9] = self.cmd * CMD_SCALE
        obs[9:21] = (self.q - self.default)[self.perm] * SCALE["dof_pos"]
        obs[21:33] = self.dq[self.perm] * SCALE["dof_vel"]
        obs[33:45] = self.action
        obs[45:47] = [math.sin(2 * math.pi * ph), math.cos(2 * math.pi * ph)]
        with torch.no_grad():
            act = self.policy(torch.from_numpy(obs).unsqueeze(0)).numpy().flatten()[:NUM_ACT]
        self.action = act
        self.target = self.default + SCALE["action"] * act[self.inv]

    def step(self, vx=0.0, vyaw=0.0):
        """走一个控制块（默认 20 ms）。vx 单位 m/s，vyaw 单位 rad/s（策略内部再乘 0.25）。"""
        self.cmd[:] = [float(vx), 0.0, float(vyaw)]
        for s in range(self.decim):
            self._apply()
            mujoco.mj_step(self.m, self.d)
            self.steps += 1
            if s == 0:
                self._update_policy()
        return self.pos()
