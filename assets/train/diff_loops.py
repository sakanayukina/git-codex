"""逐帧对比 env 与 run_ref 两套循环：同一起点、同一策略，比较 obs / target / ctrl。"""
import numpy as np
import torch

import mujoco
import env as E
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity, ACTION_SCALE

XML = "_terrain/env_plane_dump.xml"
POL = "pretrained/go2_cts_vanilla2_103.5k_0.5786.pt"


def main():
    m = mujoco.MjModel.from_xml_path(XML)
    m.opt.timestep = 0.005
    d = mujoco.MjData(m)
    qadr, dadr, aid = [], [], []
    for jn in E.JOINTS:
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn + "_joint")
        qadr.append(int(m.jnt_qposadr[j])); dadr.append(int(m.jnt_dofadr[j]))
        aid.append(next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == j))
    qadr, dadr, aid = np.array(qadr), np.array(dadr), np.array(aid)

    pol = torch.jit.load(POL); pol.eval(); pol.reset()

    # 同一起点
    d.qpos[0:3] = [0.0, 0.0, 0.45]
    d.qpos[3:7] = [1, 0, 0, 0]
    d.qpos[qadr] = DEFAULT
    mujoco.mj_forward(m, d)

    # run_ref 风格的 obs
    def ref_obs(action):
        o = np.zeros(45, dtype=np.float32)
        o[0:3] = d.qvel[3:6] * 0.25
        o[3:6] = gravity(d.qpos[3:7])
        o[6:9] = np.array([0.5, 0, 0]) * np.array([0.5, 1, 1]) if False else np.array([1.0, 0, 0])
        o[9:21] = d.qpos[qadr] - DEFAULT
        o[21:33] = d.qvel[dadr] * 0.05
        o[33:45] = action
        return o

    # env 风格的 obs
    e = E.Go2Env.__new__(E.Go2Env)
    e.m, e.d, e.bid = m, d, mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
    e.qadr, e.dadr, e.aid = qadr, dadr, aid
    e.prev_action = np.zeros(12, dtype=np.float32)
    e.steps = 0
    e.zgrid = None; e.real = False; e.half = 10.0

    action = np.zeros(12, dtype=np.float32)
    target = DEFAULT.copy()
    for k in range(40):
        # 同一步：先 4 次 PD + mj_step
        for _ in range(4):
            q, qd = d.qpos[qadr], d.qvel[dadr]
            d.ctrl[aid] = clip_torque_speed(KP * (target - q) - KD * qd, qd)
            mujoco.mj_step(m, d)
        o_ref = ref_obs(action)
        e.prev_action = action
        o_env = e._obs()
        dz = float(np.abs(o_ref - o_env).max())
        with torch.inference_mode():
            out = pol(torch.as_tensor(o_ref).unsqueeze(0))
        action = (out[0] if isinstance(out, tuple) else out).numpy().flatten()[:12]
        action = np.clip(action, -100, 100)
        target = DEFAULT + ACTION_SCALE * action
        if k < 6 or dz > 1e-4:
            print("step %2d | obs 最大差 %.2e | z=%.3f target[0..2]=%s" %
                  (k, dz, d.qpos[2], np.round(target[:3], 2)))
        if d.qpos[2] < 0.15:
            print("摔倒在 step", k); break


if __name__ == "__main__":
    main()
    run_env_loop()


def run_env_loop():
    """直接调用 env.step 走一遍，看是否摔倒。"""
    import os
    os.environ.setdefault("DSH_MODEL", "author")
    os.environ.setdefault("DSH_GROUND", "plane")
    import importlib
    import env as E2
    importlib.reload(E2)
    E2.SIM_DT, E2.DECIM = 0.005, 4
    env = E2.Go2Env(seed=0, terrain_h=0.1)
    env.real = False
    env.reset()
    env.d.qpos[0:3] = [0.0, 0.0, 0.45]
    mujoco.mj_forward(env.m, env.d)
    pol = torch.jit.load(POL); pol.eval(); pol.reset()
    obs = env._obs()
    print("env 循环：起 z=%.3f" % env.d.qpos[2])
    for k in range(60):
        o = obs.copy(); o[0:3] *= 0.25; o[6:9] = np.array([1.0, 0, 0])
        with torch.inference_mode():
            out = pol(torch.as_tensor(o).unsqueeze(0))
        act = (out[0] if isinstance(out, tuple) else out).numpy().flatten()[:12]
        act = np.clip(act, -100, 100)
        obs, r, done, info = env.step(act)
        if k % 10 == 0 or done:
            print("  step %2d z=%.3f dz=%.2f vx=%.2f done=%s" %
                  (k, env.d.qpos[2], info["z"], info["vx"], done))
        if done:
            break
