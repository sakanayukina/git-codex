"""评估训练好的 Go2 策略：在没见过的地形上确定性跑，统计距离/速度/存活。"""
import argparse
import os

import numpy as np
import torch

import os

from env import OBS_DIM, Go2Env
if os.environ.get("DSH_ENV", "") == "ref":
    from env_ref import Go2EnvRef as Go2Env
from ppo import ActorCritic

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=os.path.join(HERE, "ckpt", "last.pt"))
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--terrain-h", type=float, default=0.10)
    ap.add_argument("--steps", type=int, default=500)
    a = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = ActorCritic().to(dev)
    if os.path.exists(a.ckpt):
        ck = torch.load(a.ckpt, map_location=dev)
        net.load_state_dict(ck["net"])
        print("loaded", a.ckpt, "iter", ck.get("iter"))
    else:
        print("没有检查点，用随机初始化网络评估（作为对照基线）")
    net.eval()

    print("%-6s %-8s %-9s %-9s %-8s %s" % ("地形", "位移", "平均速度", "存活步", "结局", "末态 z"))
    for i in range(a.n):
        env = Go2Env(seed=100 + i, terrain_h=a.terrain_h)
        obs = env.reset()
        x0, y0 = float(env.d.qpos[0]), float(env.d.qpos[1])
        dist, vxs, steps, fell = 0.0, [], 0, False
        for t in range(a.steps):
            with torch.no_grad():
                mu, _ = net(torch.as_tensor(obs, dtype=torch.float32, device=dev).unsqueeze(0))
            obs, r, done, info = env.step(mu.cpu().numpy()[0])
            vxs.append(info["vx"])
            steps += 1
            if done:
                fell = info["fell"]
                break
        dist = float(np.hypot(env.d.qpos[0] - x0, env.d.qpos[1] - y0))
        print("%-6d %-8.2f %-9.2f %-9d %-8s %.2f"
              % (i, dist, float(np.mean(vxs)), steps, "摔倒" if fell else "跑完", float(env.d.qpos[2])))


if __name__ == "__main__":
    main()
