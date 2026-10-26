"""Go2 粗糙地形 locomotion 的 PPO 训练脚本。

    python ppo.py --iters 200            # 默认 16 环境
    python ppo.py --iters 2000 --save    # 存检查点
    python ppo.py --resume train/ckpt/last.pt

网络：MLP(45-256-256) 共享主干，策略头出 12 维均值 + 可学习 log_std，价值头出 1 维。
超参按 locomotion 常规：gamma .99 / lambda .95 / clip .2 / 4 epoch / lr 3e-4。
"""
import argparse
import os
import time

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Normal

from env import ACT_DIM, OBS_DIM, VecEnv

HERE = os.path.dirname(os.path.abspath(__file__))
CKPT = os.path.join(HERE, "ckpt")


class ActorCritic(nn.Module):
    def __init__(self, obs_dim=OBS_DIM, act_dim=ACT_DIM, hidden=256):
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
        )
        self.mu = nn.Linear(hidden, act_dim)
        self.v = nn.Linear(hidden, 1)
        self.log_std = nn.Parameter(torch.zeros(act_dim))
        nn.init.orthogonal_(self.mu.weight, 0.01)
        nn.init.zeros_(self.mu.bias)

    def forward(self, x):
        h = self.trunk(x)
        return self.mu(h), self.v(h).squeeze(-1)

    def act(self, x):
        mu, v = self(x)
        std = self.log_std.exp()
        dist = Normal(mu, std)
        a = dist.sample()
        return a, dist.log_prob(a).sum(-1), v

    def evaluate(self, x, a):
        mu, v = self(x)
        dist = Normal(mu, self.log_std.exp())
        return dist.log_prob(a).sum(-1), dist.entropy().sum(-1), v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=300, help="更新轮数（每轮 n*64 步）")
    ap.add_argument("--n", type=int, default=16, help="并行环境数")
    ap.add_argument("--rollout", type=int, default=64, help="每环境每轮采样步数")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--minibatch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--gamma", type=float, default=0.99)
    ap.add_argument("--lam", type=float, default=0.95)
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--ent", type=float, default=0.0)
    ap.add_argument("--terrain-h", type=float, default=0.10)
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--resume", default=None)
    a = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print("device:", dev)
    venv = VecEnv(n=a.n, terrain_h=a.terrain_h)
    net = ActorCritic().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=a.lr)
    start_iter = 0
    if a.resume and os.path.exists(a.resume):
        ck = torch.load(a.resume, map_location=dev)
        net.load_state_dict(ck["net"])
        opt.load_state_dict(ck["opt"])
        start_iter = ck.get("iter", 0)
        print("resume from", a.resume, "iter", start_iter)

    obs = venv.reset()
    obs_t = torch.as_tensor(obs, dtype=torch.float32, device=dev)
    total_steps = 0
    t0 = time.time()

    for it in range(start_iter, start_iter + a.iters):
        buf = {k: [] for k in ("obs", "act", "logp", "rew", "done", "val")}
        for _ in range(a.rollout):
            with torch.no_grad():
                act, logp, val = net.act(obs_t)
            act_np = act.cpu().numpy()
            o2, r, dn, infos = venv.step(act_np)
            buf["obs"].append(obs)
            buf["act"].append(act_np)
            buf["logp"].append(logp.cpu().numpy())
            buf["rew"].append(r)
            buf["done"].append(dn.astype(np.float32))
            buf["val"].append(val.cpu().numpy())
            obs = o2
            obs_t = torch.as_tensor(obs, dtype=torch.float32, device=dev)
            total_steps += a.n

        with torch.no_grad():
            _, last_val = net(obs_t)
        b = {k: np.asarray(v) for k, v in buf.items()}
        adv = np.zeros_like(b["rew"], dtype=np.float32)
        last = np.zeros(a.n, dtype=np.float32)
        for t in reversed(range(a.rollout)):
            next_val = last_val.cpu().numpy() if t == a.rollout - 1 else b["val"][t + 1]
            nonterm = 1.0 - b["done"][t]
            delta = b["rew"][t] + a.gamma * next_val * nonterm - b["val"][t]
            last = delta + a.gamma * a.lam * nonterm * last
            adv[t] = last
        ret = adv + b["val"]

        O = torch.as_tensor(b["obs"].reshape(-1, OBS_DIM), dtype=torch.float32, device=dev)
        A = torch.as_tensor(b["act"].reshape(-1, ACT_DIM), dtype=torch.float32, device=dev)
        LP = torch.as_tensor(b["logp"].reshape(-1), dtype=torch.float32, device=dev)
        ADV = torch.as_tensor(adv.reshape(-1), dtype=torch.float32, device=dev)
        RET = torch.as_tensor(ret.reshape(-1), dtype=torch.float32, device=dev)
        ADV = (ADV - ADV.mean()) / (ADV.std() + 1e-8)

        n = O.shape[0]
        for _ in range(a.epochs):
            idx = torch.randperm(n, device=dev)
            for s in range(0, n, a.minibatch):
                j = idx[s:s + a.minibatch]
                logp, ent, val = net.evaluate(O[j], A[j])
                ratio = (logp - LP[j]).exp()
                pg = -torch.min(ratio * ADV[j], torch.clamp(ratio, 1 - a.clip, 1 + a.clip) * ADV[j]).mean()
                vf = ((val - RET[j]) ** 2).mean()
                loss = pg + 0.5 * vf - a.ent * ent.mean()
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                opt.step()

        if (it + 1) % 10 == 0 or it == start_iter:
            ep_rew = float(b["rew"].sum(axis=0).mean())
            sps = total_steps / max(1e-9, time.time() - t0)
            print("iter %4d | step %7d | 采样奖励均值 %7.2f | %.0f steps/s"
                  % (it + 1, total_steps, ep_rew, sps), flush=True)

        if a.save and (it + 1) % 50 == 0:
            os.makedirs(CKPT, exist_ok=True)
            torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "iter": it + 1},
                       os.path.join(CKPT, "last.pt"))

    if a.save:
        os.makedirs(CKPT, exist_ok=True)
        torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "iter": start_iter + a.iters},
                   os.path.join(CKPT, "last.pt"))
        print("saved:", os.path.join(CKPT, "last.pt"))


if __name__ == "__main__":
    main()
