r"""G1 坡度训练环境（单进程版，供 PPO worker 调用）。

设计要点
- 场景用 `g1_terrain_plain.xml`（60 geom，3698 physics steps/s，比村子场景轻不了太多，
  但省掉 439 个代理球），地形在运行时用 `model.hfield_data[:]` 直接写。
- 坡度用「倾斜平面 + 粗糙度」合成，方向随机；坡度上限由课程控制。
- 观测与官方策略逐通道一致（见 `obs()`），所以可以直接微调官方 LSTM。
- 物理步 0.002、10 步一个控制块（50 Hz），PD 力矩 ±200。

    from g1_env import G1SlopeEnv
    env = G1SlopeEnv(seed=0)
    obs = env.reset(slope_deg=6.0)
    for _ in range(100):
        obs, rew, done, info = env.step(np.zeros(12))
"""
import os

import mujoco
import numpy as np

import terrain_road

HERE = os.path.dirname(os.path.abspath(__file__))
XML = os.path.join(HERE, "..", "g1_terrain_plain.xml")

KP = np.array([100, 100, 100, 150, 40, 40, 100, 100, 100, 150, 40, 40], dtype=np.float64)
KD = np.array([2, 2, 2, 4, 2, 2, 2, 2, 2, 4, 2, 2], dtype=np.float64)
DEFAULT = np.array([-0.1, 0.0, 0.0, 0.3, -0.2, 0.0,
                    -0.1, 0.0, 0.0, 0.3, -0.2, 0.0], dtype=np.float64)
SCALE = dict(ang_vel=0.25, dof_pos=1.0, dof_vel=0.05, action=0.25)
CMD_SCALE = np.array([2.0, 2.0, 0.25])
PERIOD = 0.8
DT = 0.002
DECIM = 10
NUM_OBS = 47
NUM_ACT = 12
MAX_STEPS = 260          # 10.4 s 一个 episode（v2 用 260=5.2 s，太短会让“站着”成为最优）


def _gravity(q):
    qw, qx, qy, qz = q
    return np.array([2 * (-qz * qx + qw * qy),
                     -2 * (qz * qy + qw * qx),
                     1 - 2 * (qw * qw + qz * qz)], dtype=np.float32)


class G1SlopeEnv:
    def __init__(self, seed=0, xml=XML, base_z=0.8):
        self.rng = np.random.default_rng(seed)
        self.m = terrain_road.load_model(xml, inject=False)
        self.m.opt.timestep = DT
        self.d = mujoco.MjData(self.m)
        self.base_z = float(base_z)
        self.hid = int(self.m.geom_dataid[int(np.flatnonzero(
            self.m.geom_type == mujoco.mjtGeom.mjGEOM_HFIELD)[0])])
        self.nrow = int(self.m.hfield_nrow[self.hid])
        self.ncol = int(self.m.hfield_ncol[self.hid])
        self.radius = float(self.m.hfield_size[self.hid][0])
        self.elev = float(self.m.hfield_size[self.hid][2])
        self.base = float(self.m.hfield_size[self.hid][3])
        self._calibrate_index()
        self.steps = 0
        self.cmd = np.zeros(2)
        self.action = np.zeros(NUM_ACT)
        self.prev_action = np.zeros(NUM_ACT)
        self.z_ref = self.base_z

    # ---------- 地形 ----------
    def _height(self, x, y):
        """当前写入用的合成高度（子类/训练里会替换）。"""
        return self.base_z + self._slope_tan * (x * self._sx + y * self._sy)

    def _calibrate_index(self):
        """实测 hfield_data 的行/列索引方向，避免写出镜像坡度。"""
        nr, nc = self.nrow, self.ncol
        probe = np.zeros(nr * nc, dtype=np.float32)
        # 行方向：i 线性变大
        probe[:] = np.repeat(np.linspace(0, 1, nr, dtype=np.float32), nc)
        self.m.hfield_data[:] = probe
        mujoco.mj_forward(self.m, self.d)
        hip = terrain_road.ray_height(self.m, self.d, 0.0, 20.0)
        him = terrain_road.ray_height(self.m, self.d, 0.0, -20.0)
        # 列方向
        probe[:] = np.tile(np.linspace(0, 1, nc, dtype=np.float32), nr)
        self.m.hfield_data[:] = probe
        mujoco.mj_forward(self.m, self.d)
        hjp = terrain_road.ray_height(self.m, self.d, 20.0, 0.0)
        hjm = terrain_road.ray_height(self.m, self.d, -20.0, 0.0)
        self._row_with_y = 1.0 if hip > him else -1.0
        self._col_with_x = 1.0 if hjp > hjm else -1.0

    def _grid_xy(self):
        n = self.nrow
        g = np.linspace(-self.radius, self.radius, n)
        return g

    def set_terrain(self, slope_deg, direction, rough=0.0, seed=0):
        """倾斜平面 + 粗糙度写入 hfield（物理与规划都走这份 float 数据）。"""
        g = self._grid_xy()
        X, Y = np.meshgrid(g, g)                    # X[行,列] = x, Y[行,列] = y
        a = np.radians(float(slope_deg))
        self._slope_tan = np.tan(a)
        self._sx, self._sy = np.cos(direction), np.sin(direction)
        Z = self.base_z + self._slope_tan * (X * self._sx + Y * self._sy)
        if rough > 0:
            rng = np.random.default_rng(seed)
            Z = Z + rough * (rng.standard_normal(Z.shape) * 0.5
                             + np.sin(X / 1.7) * np.cos(Y / 2.3) * 0.5)
        data = (Z - self.base) / self.elev
        if self._row_with_y < 0:
            data = data[::-1, :]
        if self._col_with_x < 0:
            data = data[:, ::-1]
        self.m.hfield_data[:] = np.ascontiguousarray(data, dtype=np.float32).ravel()
        slip = float(np.clip(1.0 - 0.15 * (slope_deg / 12.0), 0.7, 1.0))
        gid = np.flatnonzero(self.m.geom_type == mujoco.mjtGeom.mjGEOM_HFIELD)[0]
        self.m.geom_friction[gid] = [1.0 * slip, 0.02, 0.001]
        mujoco.mj_forward(self.m, self.d)

    # ---------- 生命周期 ----------
    def reset(self, slope_deg=0.0, direction=None, rough=0.0, cmd=(0.5, 0.0),
              xy=None, yaw=None, seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        if direction is None:
            direction = float(self.rng.uniform(0, 2 * np.pi))
        self.slope_deg = float(slope_deg)
        self.set_terrain(slope_deg, direction, rough=rough, seed=int(self.rng.integers(1 << 30)))
        if xy is None:
            xy = (0.0, 0.0)
        z = self.base_z + self._slope_tan * (xy[0] * self._sx + xy[1] * self._sy)
        self.d.qpos[0:3] = [xy[0], xy[1], z + 0.78]
        if yaw is None:
            yaw = direction          # 默认沿上坡方向站
        self.d.qpos[3:7] = [np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)]
        self.d.qpos[7:19] = DEFAULT
        self.d.qvel[:] = 0.0
        self.d.ctrl[:] = 0.0
        mujoco.mj_forward(self.m, self.d)
        self.steps = 0
        self.time = 0.0
        self.cmd = np.array(cmd, dtype=np.float64)
        self.action = np.zeros(NUM_ACT)
        self.prev_action = np.zeros(NUM_ACT)
        self.z_ref = float(self.d.qpos[2])
        return self.obs()

    # ---------- 观测 ----------
    def obs(self):
        t = self.steps * DT
        ph = (t % PERIOD) / PERIOD
        o = np.zeros(NUM_OBS, dtype=np.float32)
        o[0:3] = self.d.qvel[3:6] * SCALE["ang_vel"]
        o[3:6] = _gravity(self.d.qpos[3:7])
        o[6:9] = np.array([self.cmd[0], 0.0, self.cmd[1]]) * CMD_SCALE
        o[9:21] = (self.d.qpos[7:19] - DEFAULT) * SCALE["dof_pos"]
        o[21:33] = self.d.qvel[6:18] * SCALE["dof_vel"]
        o[33:45] = self.action
        o[45:47] = [np.sin(2 * np.pi * ph), np.cos(2 * np.pi * ph)]
        return o

    def up(self):
        bid = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
        return float(self.d.xmat[bid].reshape(3, 3)[2, 2])

    # ---------- 步进 ----------
    def step(self, action):
        self.prev_action = self.action
        self.action = np.clip(np.asarray(action, dtype=np.float64), -4.0, 4.0)
        target = DEFAULT + SCALE["action"] * self.action
        for _ in range(DECIM):
            tau = KP * (target - self.d.qpos[7:19]) - KD * self.d.qvel[6:18]
            self.d.ctrl[:] = np.clip(tau, -200, 200)
            mujoco.mj_step(self.m, self.d)
            self.steps += 1
        self.time = self.steps * DT

        vx, vy = self.d.qvel[0], self.d.qvel[1]
        wz = float(self.d.qvel[5])
        up = self.up()
        rew, done, info = self.reward(vx, vy, wz, up)
        return self.obs(), rew, done, info

    def reward(self, vx, vy, wz, up):
        cmd_vx, cmd_wz = float(self.cmd[0]), float(self.cmd[1])
        track_v = np.exp(-2.0 * (vx - cmd_vx) ** 2)
        track_w = np.exp(-2.0 * (wz - cmd_wz) ** 2)
        tau = KP * (DEFAULT + SCALE["action"] * self.action - self.d.qpos[7:19]) \
            - KD * self.d.qvel[6:18]
        # v3 改动（针对“不摔但不敢走”）：
        #  1) 去掉常驻的 +0.2 与 0.4*up（那是“站着不掉分”的来源）
        #  2) track_v 权重 1.0 -> 2.0，速度才值钱
        #  3) 直立只在真的直立时才给分（up>0.7 才有，最多 0.2）
        #  4) 给了前进指令却几乎不动 -> 扣分，直接杀掉“站着最安全”
        #  5) 指令为直行时罚自发偏航（航向保持）
        up_bonus = 0.3 * min(1.0, max(0.0, (up - 0.75) / 0.25))
        # 姿态门（v3.1，针对"低头猛冲"）：up<0.9 就开始连续扣分，越趴越狠
        posture = -2.0 * max(0.0, 0.9 - up)
        hold = 0.0
        if abs(cmd_wz) < 0.1:
            hold = 0.6 * (float(np.exp(-2.0 * wz * wz)) - 1.0)     # 0 -> 0, |wz|=0.5 -> -0.24
        stall = 0.0
        if cmd_vx > 0.3 and vx < 0.5 * cmd_vx:
            stall = -0.25
        rew = (2.0 * track_v + 0.3 * track_w + hold + stall + up_bonus + posture
               - 0.5 * vy * vy
               - 1e-5 * float(np.sum(np.square(np.clip(tau, -200, 200))))
               - 0.02 * float(np.sum(np.square(self.action - self.prev_action))))
        # 摔的判定门槛 0.55 -> 0.75：v3 学会了"身体前倾 60° 猛冲"，up≈0.46 也能跑起来，
        # 这种"爬着走"不算会走路；人形正常行走 up 应 ≥0.95。
        fell = up < 0.75
        if fell:
            rew -= 5.0
        timeout = self.steps >= MAX_STEPS * DECIM
        done = bool(fell or timeout)
        if done:
            rew += 0.0 if fell else 0.0
        return float(rew), done, dict(fell=bool(fell), up=up, vx=float(vx),
                                      slope=self.slope_deg, t=self.time)
