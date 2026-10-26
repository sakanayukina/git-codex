"""行为克隆：把开源 Go2 策略蒸馏进我们的 ActorCritic，作为 PPO 的初始化。

    python bc.py --envs 16 --steps 400 --epochs 30
"""
import argparse
import os

import numpy as np
import torch

from env_ref import Go2EnvRef, SIM_DT, DECIM
from ppo import ActorCritic

POL = "pretrained/go2_cts_vanilla2_103.5k_0.5786.pt"
CKPT = "ckpt/bc.pt"


def collect(n_envs, steps, noise=0.15):
    envs = [Go2EnvRef(seed=1000 + i, terrain_h=0.1) for i in range(n_envs)]
    obs = np.stack([e.reset() for e in envs])
    pol = torch.jit.load(POL); pol.eval()
    if hasattr(pol, "reset"):
        pol.reset()
    O, A = [], []
    for t in range(steps):
        a = []
        for o in obs:
            with torch.no_grad():
                out = pol(torch.as_tensor(o).unsqueeze(0))
            a.append((out[0] if isinstance(out, tuple) else out).numpy().flatten()[:12])
        a = np.stack(a).astype(np.float32)
        O.append(obs.copy()); A.append(a.copy())
        a_exec = np.clip(a + np.random.randn(*a.shape) * noise, -3, 3).astype(np.float32)
        nxt = []
        for i, e in enumerate(envs):
            o2, r, dn, info = e.step(a_exec[i])
            if dn:
                o2 = e.reset()
            nxt.append(o2)
        obs = np.stack(nxt)
        if (t + 1) % 100 == 0:
            print("  采集 %d/%d 步，样本 %d" % (t + 1, steps, len(O) * n_envs), flush=True)
    return (torch.as_tensor(np.concatenate(O), dtype=torch.float32),
            torch.as_tensor(np.concatenate(A), dtype=torch.float32))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--envs", type=int, default=16)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--epochs", type=int, default=40)
    a = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print("采集数据……")
    O, A = collect(a.envs, a.steps)
    print("样本 %d 条（obs %s, act %s）" % (O.shape[0], tuple(O.shape[1:]), tuple(A.shape[1:])))

    net = ActorCritic().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    O, A = O.to(dev), A.to(dev)
    # 固定策略网络（BC 只训 mu 头，log_std 也一起回归）
    n = O.shape[0]
    for ep in range(a.epochs):
        idx = torch.randperm(n, device=dev)
        tot = 0.0
        for s in range(0, n, 512):
            j = idx[s:s + 512]
            mu, _ = net(O[j])
            loss = ((mu - A[j]) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
            tot += float(loss) * len(j)
        if (ep + 1) % 5 == 0:
            print("  epoch %2d | MSE %.5f" % (ep + 1, tot / n), flush=True)

    os.makedirs("ckpt", exist_ok=True)
    torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "iter": 0}, CKPT)
    print("saved", CKPT)


if __name__ == "__main__":
    main()
