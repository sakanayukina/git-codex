"""同一状态下比较两套循环实际下发的 ctrl（力矩）。"""
import numpy as np
import torch
import mujoco

import env as E
E.SIM_DT, E.DECIM = 0.005, 4

POL = "pretrained/go2_cts_vanilla2_103.5k_0.5786.pt"
env = E.Go2Env(seed=0, terrain_h=0.1); env.real = False
env.reset(); env.d.qpos[0:3] = [0, 0, 0.45]; mujoco.mj_forward(env.m, env.d)
pol = torch.jit.load(POL); pol.eval(); pol.reset()

obs = env._obs()
o = obs.copy(); o[0:3] *= 0.25; o[6:9] = np.array([1.0, 0, 0])
with torch.inference_mode():
    out = pol(torch.as_tensor(o).unsqueeze(0))
act = np.clip((out[0] if isinstance(out, tuple) else out).numpy().flatten()[:12], -100, 100)
print("policy action[:3]:", np.round(act[:3], 3))
print("target[:3]:", np.round(E.DEFAULT[:3] + 0.25 * act[:3], 3))

# 手动复现 env.step 的一步，打印 ctrl
q = env.d.qpos[env.qadr]; qd = env.d.qvel[env.dadr]
target = E.DEFAULT + E.ACTION_SCALE * act
eff = E.KP * (target - q) - E.KD * qd
ctrl = E.clip_torque_speed(eff, qd)
print("env 侧 ctrl[:3]:", np.round(ctrl[:3], 2), "KP[0]=", E.KP[0], "aid[:3]=", env.aid[:3])
print("env model nu=%d, actuator names[:3]=%s" % (
    env.m.nu, [mujoco.mj_id2name(env.m, mujoco.mjtObj.mjOBJ_ACTUATOR, i) for i in range(3)]))
print("aid 对应的执行器名:", [mujoco.mj_id2name(env.m, mujoco.mjtObj.mjOBJ_ACTUATOR, i) for i in env.aid[:3]])
print("qadr 对应关节:", [mujoco.mj_id2name(env.m, mujoco.mjtObj.mjOBJ_JOINT, env.m.jnt_qposadr.tolist().index(a)) if a in env.m.jnt_qposadr.tolist() else '?' for a in env.qadr[:3]])
print("joint of aid[0]:", mujoco.mj_id2name(env.m, mujoco.mjtObj.mjOBJ_JOINT, env.m.actuator_trnid[env.aid[0]][0]))
print("qpos joints[:3]:", [mujoco.mj_id2name(env.m, mujoco.mjtObj.mjOBJ_JOINT, j) for j in range(1, 4)])
