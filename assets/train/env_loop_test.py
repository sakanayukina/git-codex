"""单独用 env.step 跑策略，隔离 env.step 的问题。"""
import numpy as np
import torch

import mujoco
import env as E

POL = "pretrained/go2_cts_vanilla2_103.5k_0.5786.pt"
E.SIM_DT, E.DECIM = 0.005, 4

env = E.Go2Env(seed=0, terrain_h=0.1)
env.real = False
env.reset()
env.d.qpos[0:3] = [0.0, 0.0, 0.45]
mujoco.mj_forward(env.m, env.d)
pol = torch.jit.load(POL); pol.eval(); pol.reset()
obs = env._obs()
print("起 z=%.3f, KP=%s KD=%s DECIM=%d SIM_DT=%.3f" %
      (env.d.qpos[2], E.KP[0], E.KD[0], E.DECIM, E.SIM_DT))
for k in range(80):
    o = obs.copy(); o[0:3] *= 0.25; o[6:9] = np.array([1.0, 0, 0])
    with torch.inference_mode():
        out = pol(torch.as_tensor(o).unsqueeze(0))
    act = (out[0] if isinstance(out, tuple) else out).numpy().flatten()[:12]
    obs, r, done, info = env.step(np.clip(act, -100, 100))
    if k % 10 == 0 or done:
        print("  step %2d z=%.3f dz=%.2f vx=%.2f done=%s" % (k, env.d.qpos[2], info["z"], info["vx"], done))
    if done:
        break
