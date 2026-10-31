r"""把官方 G1 平地策略蒸馏成一个可训练的 MLP（BC），作为坡度 PPO 的起点。

为什么要蒸馏：官方权重是 `motion.pt`（TorchScript，推理专用）。要往后继续训练
（PPO 微调跑到坡面上）必须有一份可求导的参数，所以先行为克隆出来。

流程：
    python g1_bc.py --collect 30000 --epochs 300        # 采数据 + 训练 + 存盘 + 回放验证
    python g1_bc.py --eval-only                         # 只做回放对比

产物：
    assets/train/ckpt/g1_bc.pt        MLP 权重（state_dict，PPO 从这里初始化）
    assets/train/ckpt/g1_bc_ts.pt     TorchScript（G1Walker(policy_fn=...) 直接可用）
"""
import argparse
import os

import mujoco
import numpy as np
import torch
import torch.nn as nn

import terrain_road
from g1_walker import G1Walker, DEFAULT

HERE = os.path.dirname(os.path.abspath(__file__))
XML = os.path.join(HERE, "..", "g1_terrain_plain.xml")
CKPT = os.path.join(HERE, "ckpt")
FLAT_Z = 0.8          # 平地高程（米）


def flatten_terrain(m, z=FLAT_Z):
    """把 hfield 抹成 z 米高的绝对平地（base + data*elev）。"""
    base = float(m.hfield_size[0][3])
    elev = float(m.hfield_size[0][2])
    m.hfield_data[:] = (z - base) / elev


class MLP(nn.Module):
    def __init__(self, nin=47, nout=12, hidden=256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(nin, hidden), nn.ELU(),
            nn.Linear(hidden, hidden), nn.ELU(),
            nn.Linear(hidden, nout),
        )
        # 初始化为小输出，避免一开始就跑飞
        nn.init.zeros_(self.net[-1].bias)
        nn.init.normal_(self.net[-1].weight, std=0.01)

    def forward(self, x):
        return self.net(x)


def spawn_flat(m, d, xy=(0.0, 0.0)):
    d.qpos[0:3] = [xy[0], xy[1], FLAT_Z + 0.78]
    d.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    d.qpos[7:19] = DEFAULT
    d.qvel[:] = 0.0
    d.ctrl[:] = 0.0
    mujoco.mj_forward(m, d)


def collect(n_target=30000, seed=0, verbose=True):
    rng = np.random.default_rng(seed)
    m = terrain_road.load_model(XML, inject=False)
    flatten_terrain(m)
    d = mujoco.MjData(m)
    spawn_flat(m, d)
    w = G1Walker(m, d)
    w.record = []

    cmds = [(0.0, 0.0), (0.3, 0.0), (0.5, 0.0), (0.8, 0.0),
            (0.5, 0.2), (0.5, -0.2), (0.3, 0.15), (0.7, -0.15)]
    k = 0
    while len(w.record) < n_target:
        vx, vyaw = cmds[k % len(cmds)]
        for _ in range(100):                      # 每个指令 2 s
            w.step(vx, vyaw)
            if w.up() < 0.3:                      # 摔了就原地重开，walker 不重建（相位连续）
                spawn_flat(m, d, xy=(float(rng.uniform(-2, 2)), float(rng.uniform(-2, 2))))
                break
            if len(w.record) >= n_target:
                break
        k += 1
        if verbose and k % 20 == 0:
            print("  collected %d / %d" % (len(w.record), n_target), flush=True)
    obs = np.stack([r[0] for r in w.record])
    act = np.stack([r[1] for r in w.record])
    return obs, act


def train(obs, act, epochs=300, batch=1024, lr=1e-3, device="cuda"):
    dev = device if (device == "cuda" and torch.cuda.is_available()) else "cpu"
    X = torch.from_numpy(obs).float()
    Y = torch.from_numpy(act).float()
    net = MLP().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    n = len(X)
    for ep in range(epochs):
        perm = torch.randperm(n)
        tot = 0.0
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            xb, yb = X[idx].to(dev), Y[idx].to(dev)
            pred = net(xb)
            loss = ((pred - yb) ** 2).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(loss) * len(idx)
        sch.step()
        if ep % 25 == 0 or ep == epochs - 1:
            print("  epoch %3d  mse %.5f  (rmse %.4f)" % (ep, tot / n, (tot / n) ** 0.5),
                  flush=True)
    net.eval()
    return net


def evaluate(policy_fn, seconds=10.0, vx=0.5, flat=True):
    m = terrain_road.load_model(XML, inject=False)
    if flat:
        flatten_terrain(m)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    if flat:
        spawn_flat(m, d)
    else:
        gz = terrain_road.ray_height(m, d, -4.0, -62.0)
        d.qpos[0:3] = [-4.0, -62.0, gz + 0.78]
        d.qpos[7:19] = DEFAULT
        mujoco.mj_forward(m, d)
    w = G1Walker(m, d, policy_fn=policy_fn)
    start = np.array([d.qpos[0], d.qpos[1]])
    fell = None
    for k in range(int(seconds / 0.02)):
        w.step(vx, 0.0)
        if w.up() < 0.2:
            fell = (k + 1) * 0.02
            break
    pos = w.pos()
    return dict(dist=float(np.linalg.norm(pos - start)), up=w.up(), fell=fell,
                t=(fell or seconds))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", type=int, default=30000)
    ap.add_argument("--epochs", type=int, default=300)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--eval-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(CKPT, exist_ok=True)

    if not a.eval_only:
        print("① 用官方策略采数据（平地）…")
        obs, act = collect(a.collect)
        print("   样本 %d，obs %s act %s" % (len(obs), obs.shape, act.shape))
        np.savez(os.path.join(CKPT, "g1_bc_data.npz"), obs=obs, act=act)

        print("② 训练 MLP 学生 …")
        net = train(obs, act, epochs=a.epochs, device=a.device)
        torch.save(net.state_dict(), os.path.join(CKPT, "g1_bc.pt"))
        ts = torch.jit.script(net.cpu())
        ts.save(os.path.join(CKPT, "g1_bc_ts.pt"))
        print("   已存 %s / g1_bc_ts.pt" % os.path.join(CKPT, "g1_bc.pt"))

    print("③ 回放对比（平地，vx 0.5，10 s）")
    path = os.path.join(CKPT, "g1_bc_ts.pt")
    if not os.path.exists(path):
        raise SystemExit("缺少 %s，先跑训练" % path)
    stu = torch.jit.load(path)
    ro = evaluate(None, seconds=10.0)                 # 官方
    rs = evaluate(stu, seconds=10.0)                  # 学生
    print("   官方: 位移 %.2f m, up %.3f, 摔 %s" % (ro["dist"], ro["up"], ro["fell"]))
    print("   学生: 位移 %.2f m, up %.3f, 摔 %s" % (rs["dist"], rs["up"], rs["fell"]))


if __name__ == "__main__":
    main()
