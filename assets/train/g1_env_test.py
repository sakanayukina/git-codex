r"""自测 g1_env：坡度方向、平地行走与坡面表现（用官方 LSTM 策略闭环）。

    & "C:/Users/18967/anaconda3/envs/mujoco/python.exe" g1_env_test.py
"""
import numpy as np
import torch

import terrain_road
from g1_env import DECIM, DT, G1SlopeEnv, MAX_STEPS
from g1_policy_net import G1Actor


def slope_check(env):
    print("== 坡度方向自检 ==")
    for deg, direction in ((10.0, 0.0), (10.0, np.pi / 2), (6.0, np.pi)):
        env.set_terrain(deg, direction)
        m, d = env.m, env.d
        hxp = terrain_road.ray_height(m, d, 5.0, 0.0)
        hxm = terrain_road.ray_height(m, d, -5.0, 0.0)
        hyp = terrain_road.ray_height(m, d, 0.0, 5.0)
        hym = terrain_road.ray_height(m, d, 0.0, -5.0)
        print("  %.0f° dir=%5.1f°  Δh(+x,-x)=%+.3f  Δh(+y,-y)=%+.3f  (期望 %+.3f / %+.3f)"
              % (deg, np.degrees(direction), hxp - hxm, hyp - hym,
                 10 * np.tan(np.radians(deg)) * np.cos(direction),
                 10 * np.tan(np.radians(deg)) * np.sin(direction)))


def rollout(env, actor, slope, direction=None, blocks=300, vx=0.5, label=""):
    obs = env.reset(slope_deg=slope, direction=direction, rough=0.0, cmd=(vx, 0.0))
    if hasattr(actor, "reset"):
        actor.reset()
    p0 = env.d.qpos[0:2].copy()
    up_min = 1.0
    fell_at = None
    vxs = []
    for k in range(blocks):
        with torch.no_grad():
            act = actor(torch.from_numpy(obs).unsqueeze(0)).numpy().flatten()
        obs, rew, done, info = env.step(act)
        up_min = min(up_min, info["up"])
        vxs.append(info["vx"])
        if done:
            if info["fell"]:
                fell_at = (k + 1) * DECIM * DT
            break
    p1 = env.d.qpos[0:2]
    dist = float(np.hypot(*(p1 - p0)))
    print("  %-16s slope=%4.1f°  dist=%6.2f m  %5.2f s  mean vx=%5.2f  up_min=%5.2f  %s"
          % (label, slope, dist, (k + 1) * DECIM * DT, float(np.mean(vxs)), up_min,
             ("摔 @%.1f s" % fell_at) if fell_at else "不摔"))
    return dist, fell_at


def main():
    env = G1SlopeEnv(seed=0)
    print("env: hfield %dx%d radius %.1f elev %.2f base %.2f  row_with_y=%+.0f col_with_x=%+.0f"
          % (env.nrow, env.ncol, env.radius, env.elev, env.base,
             env._row_with_y, env._col_with_x))
    slope_check(env)

    actor = G1Actor.from_official()
    print("== 官方策略在 env 里的表现 ==")
    rollout(env, actor, 0.0, blocks=300, label="flat 0°")
    rollout(env, actor, 2.0, blocks=300, label="slope 2°")
    rollout(env, actor, 4.0, blocks=300, label="slope 4°")
    rollout(env, actor, 6.0, blocks=200, label="slope 6°")
    rollout(env, actor, 8.0, blocks=120, label="slope 8°")


if __name__ == "__main__":
    main()
