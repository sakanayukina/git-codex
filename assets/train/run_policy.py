"""跑外部 TorchScript 策略（如社区 Go2 的 45 维 legged_gym 接口）在我们的地形上。

    python run_policy.py --policy pretrained/xxx.pt --terrain-h 0.10 --n 5
可选缩放：--ang-scale / --dofvel-scale / --cmd-scale，用于对齐不同训练配置。
"""
import argparse

import mujoco as _mj
import numpy as np
import torch

from env import ACT_DIM, DECIM, SIM_DT, CMD, DEFAULT, Go2Env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--terrain-h", type=float, default=0.10)
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--ang-scale", type=float, default=1.0)
    ap.add_argument("--dofvel-scale", type=float, default=0.05)
    ap.add_argument("--cmd-scale", type=float, default=1.0)
    ap.add_argument("--action-scale", type=float, default=0.25)
    ap.add_argument("--vx", type=float, default=0.5)
    ap.add_argument("--perm", default="", help="策略关节顺序映射")
    ap.add_argument("--defaults", default="", help="12 个默认关节角，逗号分隔")
    ap.add_argument("--kp", type=float, default=0.0, help=">0 时覆盖伺服 kp")
    ap.add_argument("--kd", type=float, default=0.0)
    ap.add_argument("--cmd-scale-x", type=float, default=1.0)
    ap.add_argument("--sim-dt", type=float, default=0.0, help=">0 时覆盖物理步长（参考配置 0.005）")
    ap.add_argument("--decim", type=int, default=0, help=">0 时覆盖控制抽取（参考配置 4）")
    ap.add_argument("--solver-newton", action="store_true", help="用参考配置的 newton 求解器")
    a = ap.parse_args()

    import env as E
    if a.defaults:
        E.DEFAULT[:] = [float(x) for x in a.defaults.split(",")]
        print("default angles:", E.DEFAULT.tolist())
    if a.kp > 0:
        E.KP[:] = a.kp
        print("kp:", a.kp)
    if a.kd > 0:
        E.KD[:] = a.kd
        print("kd:", a.kd)
    E.CMD[0] = a.vx
    pol = torch.jit.load(a.policy)
    perm = np.array([int(x) for x in a.perm.split(",")] if a.perm else list(range(12)))
    inv = np.argsort(perm)
    print("policy:", a.policy)

    print("%-6s %-8s %-9s %-9s %-8s %s" % ("地形", "位移", "平均速度", "存活步", "结局", "末态z"))
    tot_d, tot_s = [], []
    for i in range(a.n):
        env = Go2Env(seed=200 + i, terrain_h=a.terrain_h)
        if a.sim_dt > 0:
            env.m.opt.timestep = a.sim_dt
        if a.solver_newton:
            env.m.opt.solver = _mj.mjtSolver.mjSOL_NEWTON
            env.m.opt.iterations = 100
            env.m.opt.ls_iterations = 50
        if hasattr(pol, "reset"):
            pol.reset()
        if hasattr(env, '_reset_policy'):
            pass
        obs = env.reset()
        x0, y0 = float(env.d.qpos[0]), float(env.d.qpos[1])
        vxs, steps, fell = [], 0, False
        cmd = CMD.copy()
        cmd[0] = a.vx
        for _ in range(a.steps):
            o = obs.copy()
            o[0:3] *= a.ang_scale             # 角速度缩放
            o[6:9] = cmd * a.cmd_scale
            o[6] *= a.cmd_scale_x / max(a.cmd_scale, 1e-6)
            o[21:33] = o[21:33] / 0.05 * a.dofvel_scale
            o[9:21] = o[9:21][perm]           # 关节角按策略顺序重排
            o[21:33] = o[21:33][perm]
            with torch.no_grad():
                out = pol(torch.as_tensor(o, dtype=torch.float32).unsqueeze(0))
            act = (out[0] if isinstance(out, tuple) else out).numpy().flatten()[:ACT_DIM]
            act = act[inv]                    # 动作映射回模型关节顺序
            obs, r, done, info = env.step(act)
            vxs.append(info["vx"])
            steps += 1
            if done:
                fell = info["fell"]
                break
        dist = float(np.hypot(env.d.qpos[0] - x0, env.d.qpos[1] - y0))
        tot_d.append(dist)
        tot_s.append(steps)
        print("%-6d %-8.2f %-9.2f %-9d %-8s %.2f"
              % (i, dist, float(np.mean(vxs)), steps, "摔倒" if fell else "跑完",
                 float(env.d.qpos[2])))
    print("平均：位移 %.2f m，存活 %.0f 步（%.1f 秒）"
          % (np.mean(tot_d), np.mean(tot_s), np.mean(tot_s) * SIM_DT * DECIM))


if __name__ == "__main__":
    main()
