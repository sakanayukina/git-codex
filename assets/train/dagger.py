"""DAgger：学生自己走（会进入临近摔倒的状态），由老师给出正确动作标签，再训练。

    python dagger.py --rounds 3 --envs 24 --steps 400
"""
import argparse
import os

import numpy as np
import torch

from env_ref import Go2EnvRef
from ppo import ActorCritic

TEACHER = "pretrained/go2_cts_vanilla2_103.5k_0.5786.pt"
CKPT = "ckpt/bc.pt"


def teacher_actions(pol, obs):
    a = []
    for o in obs:
        with torch.no_grad():
            out = pol(torch.as_tensor(o).unsqueeze(0))
        a.append((out[0] if isinstance(out, tuple) else out).numpy().flatten()[:12])
    return np.stack(a).astype(np.float32)


def rollout(envs, teach, net, steps, noise=0.2, dev="cuda"):
    obs = np.stack([e.reset() for e in envs])
    O, A = [], []
    for t in range(steps):
        lab = teacher_actions(teach, obs)
        O.append(obs.copy()); A.append(lab.copy())
        with torch.no_grad():
            mu, _ = net(torch.as_tensor(obs, dtype=torch.float32, device=dev))
        act = mu.cpu().numpy() + np.random.randn(len(envs), 12) * noise
        act = np.clip(act, -3, 3).astype(np.float32)
        nxt = []
        for i, e in enumerate(envs):
            o2, r, dn, info = e.step(act[i])
            if dn:
                o2 = e.reset()
            nxt.append(o2)
        obs = np.stack(nxt)
    return (torch.as_tensor(np.concatenate(O), dtype=torch.float32),
            torch.as_tensor(np.concatenate(A), dtype=torch.float32))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--envs", type=int, default=24)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--epochs", type=int, default=60)
    a = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = ActorCritic().to(dev)
    if os.path.exists(CKPT):
        net.load_state_dict(torch.load(CKPT, map_location=dev)["net"])
        print("从", CKPT, "继续")
    opt = torch.optim.Adam(net.parameters(), lr=5e-4)
    teach = torch.jit.load(TEACHER); teach.eval()
    envs = [Go2EnvRef(seed=2000 + i, terrain_h=0.1) for i in range(a.envs)]

    for r in range(a.rounds):
        print("=== DAgger 第 %d 轮 ===" % (r + 1))
        O, A = rollout(envs, teach, net, a.steps, noise=0.14 + 0.04 * r, dev=dev)
        print("  样本 %d" % O.shape[0])
        O, A = O.to(dev), A.to(dev)
        n = O.shape[0]
        for ep in range(a.epochs):
            idx = torch.randperm(n, device=dev)
            for s in range(0, n, 512):
                j = idx[s:s + 512]
                mu, _ = net(O[j])
                loss = ((mu - A[j]) ** 2).mean()
                opt.zero_grad(); loss.backward(); opt.step()
            if (ep + 1) % 20 == 0:
                print("    epoch %2d | MSE %.4f" % (ep + 1, float(loss)))
        torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "iter": r + 1}, CKPT)
        print("  保存", CKPT)


if __name__ == "__main__":
    main()
