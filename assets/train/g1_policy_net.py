r"""官方 G1 策略的纯净 PyTorch 重建（可求导），用于 PPO 微调。

官方 `motion.pt` 是 TorchScript，里面其实是：

    obs(47) → LSTM(hidden=256→64) → Linear(64→32) → ELU → Linear(32→12)

`state_dict` 里有 8 个参数张量（memory.* 4 个、actor.* 4 个）外加 hidden_state /
cell_state（1×1×64 缓冲）。TorchScript 图里有 in-place 操作，直接 backward 会报
"variable needed for gradient computation has been modified by an inplace operation"，
所以这里把权重搬到普通 `nn.Module` 里，梯度就正常了。

用法：
    from g1_policy_net import G1Actor
    net = G1Actor.from_official()        # 权重与官方逐位相同
    net.reset()
    a = net(obs)                         # (B,47) -> (B,12)

    python g1_policy_net.py --probe      # 探测 actor 的真实接线（out/h × 激活函数）
    python g1_policy_net.py --verify     # 与 TorchScript 逐步比对
"""
import argparse
import os

import torch
import torch.nn as nn

HERE = os.path.dirname(os.path.abspath(__file__))
OFFICIAL = os.path.join(HERE, "..", "props", "robots", "g1", "motion.pt")

NIN, NHID, NMID, NOUT = 47, 64, 32, 12
ACTS = {"elu": nn.ELU, "relu": nn.ReLU, "tanh": nn.Tanh, "silu": nn.SiLU, "id": nn.Identity}


class G1Actor(nn.Module):
    """与官方一致的 LSTM + 两层 MLP actor。"""

    def __init__(self, nin=NIN, nhid=NHID, nmid=NMID, nout=NOUT, act="elu", source="out"):
        super().__init__()
        self.memory = nn.LSTM(nin, nhid)
        self.actor = nn.Sequential(nn.Linear(nhid, nmid), ACTS[act](), nn.Linear(nmid, nout))
        self.source = source          # "out"=LSTM 输出， "h"=隐状态
        self.nhid = nhid
        self._h = None
        self._c = None

    def reset(self, batch=1):
        self._h = torch.zeros(1, batch, self.nhid, dtype=torch.float32)
        self._c = torch.zeros(1, batch, self.nhid, dtype=torch.float32)

    def forward(self, obs, detach_state=True):
        if self._h is None or self._h.size(1) != obs.size(0):
            self.reset(obs.size(0))
        out, (h, c) = self.memory(obs.unsqueeze(0), (self._h, self._c))
        if detach_state:
            self._h, self._c = h.detach(), c.detach()
        else:
            self._h, self._c = h, c
        feat = out.squeeze(0) if self.source == "out" else h.squeeze(0)
        return self.actor(feat)

    # ---- 显式状态接口（训练用：不改内部状态，便于分块反传） ----
    def step(self, obs, h=None, c=None):
        """单步推理。obs (B,47) → (mu (B,12), h (1,B,64), c (1,B,64))。"""
        B = obs.size(0)
        if h is None or c is None:
            h = torch.zeros(1, B, self.nhid, dtype=obs.dtype, device=obs.device)
            c = torch.zeros(1, B, self.nhid, dtype=obs.dtype, device=obs.device)
        out, (h2, c2) = self.memory(obs.unsqueeze(0), (h, c))
        feat = out.squeeze(0) if self.source == "out" else h2.squeeze(0)
        return self.actor(feat), h2, c2

    def seq(self, obs, h0, c0):
        """序列推理。obs (B,L,47) → mu (B,L,12)。h0/c0 形状 (1,B,64)。"""
        out, _ = self.memory(obs.permute(1, 0, 2), (h0, c0))     # (L,B,64)
        mu = self.actor(out)                                      # (L,B,12)
        return mu.permute(1, 0, 2)

    @staticmethod
    def from_official(path=OFFICIAL, **kw):
        sd = torch.jit.load(path, map_location="cpu").state_dict()
        net = G1Actor(**kw)
        net.load_state_dict({k: v for k, v in sd.items() if not k.endswith("_state")})
        net.eval()
        return net


def _scripted(path=OFFICIAL):
    p = torch.jit.load(path, map_location="cpu")
    p.eval()
    if hasattr(p, "reset_memory"):
        p.reset_memory()
    return p


def probe(path=OFFICIAL, steps=6, seed=0):
    """暴力搜索 actor 的接线：LSTM 输出 vs 隐状态 × 激活函数。"""
    torch.manual_seed(seed)
    sd = torch.jit.load(path, map_location="cpu").state_dict()
    W1, b1 = sd["actor.0.weight"], sd["actor.0.bias"]
    W2, b2 = sd["actor.2.weight"], sd["actor.2.bias"]
    lstm = nn.LSTM(NIN, NHID)
    lstm.load_state_dict({k[len("memory."):]: v for k, v in sd.items()
                          if k.startswith("memory.")})
    lstm.eval()

    scripted = _scripted(path)
    obses = [torch.randn(1, NIN) for _ in range(steps)]
    targets = [scripted(o).flatten().detach() for o in obses]

    h = torch.zeros(1, 1, NHID)
    c = torch.zeros(1, 1, NHID)
    outs, hs = [], []
    with torch.no_grad():
        for o in obses:
            out, (h, c) = lstm(o.unsqueeze(0), (h, c))
            outs.append(out.flatten())
            hs.append(h.flatten())

    best = None
    for src in ("out", "h"):
        for name, cls in ACTS.items():
            f = cls()
            err = 0.0
            with torch.no_grad():
                for i in range(steps):
                    v = outs[i] if src == "out" else hs[i]
                    y = W2 @ f(W1 @ v + b1) + b2
                    err = max(err, float((y - targets[i]).abs().max()))
            print("  source=%-3s act=%-5s maxdiff %.6f" % (src, name, err))
            if err < 1e-4 and (best is None or err < best[2]):
                best = (src, name, err)
    print("==> 最佳: %s" % (best,))
    return best


def verify(path=OFFICIAL, steps=50, seed=0):
    """用 from_official 的网络逐步复现 TorchScript 的输出。"""
    torch.manual_seed(seed)
    net = G1Actor.from_official(path)
    net.reset()
    scripted = _scripted(path)
    worst = 0.0
    with torch.no_grad():
        for i in range(steps):
            o = torch.randn(1, NIN)
            a = scripted(o).flatten()
            b = net(o).flatten()
            worst = max(worst, float((a - b).abs().max()))
    print("verify: %d 步, 与官方最大偏差 %.3e" % (steps, worst))
    return worst


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.probe:
        probe()
    if a.verify:
        verify()
    if not (a.probe or a.verify):
        verify()
