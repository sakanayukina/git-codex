r"""G1 slope PPO trainer (LSTM actor, threaded rollouts, chunked BPTT, KL trust region).

 MuJoCo 3.3.2 ?`mj_step` ?GIL?8 
23999 physics steps/s2400 ?s 3692?Windows 
multiprocessing.Pipe` ?PermissionError +  dict?


----
- --workers` ?`G1SlopeEnv` ?
-  GPU  (h, c) ?BPTT  `--chunk`?
- ?`--slope-start` ?`--slope-max`?`--flat-prob` ?

    & "C:/Users/18967/anaconda3/envs/mujoco/python.exe" g1_ppo.py --iters 3 --workers 4 --steps 48
    & "C:/Users/18967/anaconda3/envs/mujoco/python.exe" g1_ppo.py --iters 3000 --workers 8

ckpt/g1_slope_ppo.pt`tate_dict? `.json`?
"""
import argparse
import copy
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import torch
import torch.nn as nn

import g1_eval as ev
import g1_env as E
from g1_policy_net import G1Actor

HERE = os.path.dirname(os.path.abspath(__file__))
CKPT = os.path.join(HERE, "ckpt")
DEV = "cuda" if torch.cuda.is_available() else "cpu"
NHID = 64


def gauss_logp(a, mu, std):
    return float(np.sum(-0.5 * ((a - mu) ** 2) / (std ** 2) - np.log(std) - 0.5 * np.log(2 * np.pi)))


# ---------------------------------------------------------------- rollout worker
class RolloutWorker:
    def __init__(self, wid):
        self.wid = wid
        self.env = E.G1SlopeEnv(seed=1000 + wid)
        self.actor = G1Actor.from_official()
        self.actor.eval()
        self.h = self.c = None
        self.obs = None

    def _reset(self, plan):
        slope_max, flat_prob, rough, seed = plan
        rng = np.random.default_rng(seed * 1000 + self.wid)
        if rng.random() < flat_prob:
            slope = float(rng.uniform(0.0, 1.0))
        else:
            slope = float(rng.uniform(0.0, max(1e-6, slope_max)))
        vx = float(rng.uniform(-0.2, 1.0))
        wz = float(rng.uniform(-0.5, 0.5))
        self.obs = self.env.reset(slope_deg=slope, direction=float(rng.uniform(0, 2 * np.pi)),
                                 rough=float(rng.uniform(0.0, rough)), cmd=(vx, wz),
                                 yaw=float(rng.uniform(0, 2 * np.pi)),
                                 seed=int(rng.integers(1 << 30)))
        self.h = self.c = None

    def run(self, sd, plan, std, n_steps):
        self.actor.load_state_dict(sd)
        self._reset(plan)          #  buffer ?burn-in
        O = np.zeros((n_steps, E.NUM_OBS), dtype=np.float32)
        A = np.zeros((n_steps, E.NUM_ACT), dtype=np.float32)
        LP = np.zeros(n_steps, dtype=np.float32)
        R = np.zeros(n_steps, dtype=np.float32)
        D = np.zeros(n_steps, dtype=np.float32)
        H = np.zeros((n_steps, NHID), dtype=np.float32)
        C = np.zeros((n_steps, NHID), dtype=np.float32)
        n_done = 0
        for t in range(n_steps):
            with torch.no_grad():
                h_in, c_in = self.h, self.c
                mu_t, self.h, self.c = self.actor.step(
                    torch.from_numpy(self.obs).unsqueeze(0), self.h, self.c)
            mu = mu_t.numpy().flatten()
            # ?? H[s] ?s 
            H[t] = (torch.zeros_like(self.h) if h_in is None else h_in).numpy().flatten()
            C[t] = (torch.zeros_like(self.c) if c_in is None else c_in).numpy().flatten()
            act = (mu + std * np.random.randn(E.NUM_ACT).astype(np.float32)).astype(np.float32)
            O[t] = self.obs
            A[t] = act
            LP[t] = gauss_logp(act, mu, std)
            self.obs, rew, done, inf = self.env.step(act)
            R[t] = rew
            D[t] = float(done)
            if done:
                n_done += 1
                self._reset(plan)
        return dict(obs=O, act=A, logp=LP, rew=R, done=D, h=H, c=C,
                    last=self.obs.copy(), n_done=n_done)


# ---------------------------------------------------------------- nets
class ValueNet(nn.Module):
    def __init__(self, nin=E.NUM_OBS, hid=256):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(nin, hid), nn.ELU(),
                                 nn.Linear(hid, hid), nn.ELU(),
                                 nn.Linear(hid, 1))

    def forward(self, x):
        return self.net(x).squeeze(-1)


class LogStd(nn.Module):
    def __init__(self, n=E.NUM_ACT, init=-1.2):
        super().__init__()
        self.log_std = nn.Parameter(torch.full((n,), float(init)))

    def forward(self):
        return self.log_std.clamp(-3.0, 0.5).exp()


# ---------------------------------------------------------------- train
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--steps", type=int, default=192, help=" worker ?")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--chunk", type=int, default=16, help="BPTT ")
    ap.add_argument("--burn", type=int, default=32, help="burn-in ")
    ap.add_argument("--minibatch", type=int, default=24)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--lr-value", type=float, default=1e-3)
    ap.add_argument("--gamma", type=float, default=0.995)
    ap.add_argument("--lam", type=float, default=0.95)
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--kl-stop", type=float, default=0.02)
    ap.add_argument("--kl-target", type=float, default=0.02, help=" KL")
    ap.add_argument("--lr-max", type=float, default=1e-4)
    ap.add_argument("--slope-start", type=float, default=2.0)
    ap.add_argument("--slope-max", type=float, default=12.0)
    ap.add_argument("--flat-prob", type=float, default=0.2)
    ap.add_argument("--rough", type=float, default=0.02)
    ap.add_argument("--anneal", type=float, default=0.4)
    ap.add_argument("--std-init", type=float, default=-1.0)
    ap.add_argument("--init", default="")
    ap.add_argument("--anchor", type=float, default=0.0,
                    help=" mu 0=")
    ap.add_argument("--freeze-lstm", action="store_true",
                    help=" LSTM")
    ap.add_argument("--out", default=os.path.join(CKPT, "g1_slope_ppo"))
    ap.add_argument("--save-every", type=int, default=25)
    ap.add_argument("--keep-best", action="store_true", default=True)
    ap.add_argument("--eval-every", type=int, default=0,
                    help="?N 4/6/8/10 ?x ??")
    args = ap.parse_args()
    os.makedirs(CKPT, exist_ok=True)
    torch.set_num_threads(2)

    workers = [RolloutWorker(i) for i in range(args.workers)]
    pool = ThreadPoolExecutor(max_workers=args.workers)

    actor = G1Actor.from_official()
    if args.init and os.path.exists(args.init):
        actor.load_state_dict(torch.load(args.init, map_location="cpu"))
        print("warm start from %s" % args.init)
    ref_actor = None
    if args.anchor > 0.0:
        ref_actor = copy.deepcopy(actor).to(DEV).eval()
        for _p in ref_actor.parameters():
            _p.requires_grad_(False)
        print("[anchor] reference policy frozen, coef=%.2f" % args.anchor)
    actor.to(DEV).eval()
    val = ValueNet().to(DEV)
    logstd = LogStd(init=args.std_init).to(DEV)
    if args.freeze_lstm:
        for _n, _p in actor.named_parameters():
            if _n.startswith("memory"):
                _p.requires_grad_(False)
        _tr = [p for p in actor.parameters() if p.requires_grad]
        print("[freeze] LSTM frozen, trainable tensors: %d / %d" % (len(_tr), len(list(actor.parameters()))))
        opt_a = torch.optim.Adam(_tr, lr=args.lr)
    else:
        opt_a = torch.optim.Adam(actor.parameters(), lr=args.lr)
    opt_v = torch.optim.Adam(val.parameters(), lr=args.lr_value)
    opt_s = torch.optim.Adam(logstd.parameters(), lr=args.lr)

    W, T, L = args.workers, args.steps, args.chunk
    log = []
    t0 = time.time()
    for it in range(1, args.iters + 1):
        frac = min(1.0, it / max(1.0, args.anneal * args.iters))
        slope_max = args.slope_start + (args.slope_max - args.slope_start) * frac
        std = logstd().detach().cpu().numpy().astype(np.float32)
        sd = {k: v.detach().cpu() for k, v in actor.state_dict().items()}
        prev_sd = {k: v.clone() for k, v in sd.items()}
        plan = (slope_max, args.flat_prob, args.rough, it * 7919)
        futs = [pool.submit(w.run, sd, plan, std, T) for w in workers]
        bufs = [f.result() for f in futs]

        obs = torch.as_tensor(np.concatenate([b["obs"] for b in bufs]), dtype=torch.float32, device=DEV)
        act = torch.as_tensor(np.concatenate([b["act"] for b in bufs]), dtype=torch.float32, device=DEV)
        logp = torch.as_tensor(np.concatenate([b["logp"] for b in bufs]), dtype=torch.float32, device=DEV)
        rew = torch.as_tensor(np.concatenate([b["rew"] for b in bufs]), dtype=torch.float32, device=DEV)
        done = torch.as_tensor(np.concatenate([b["done"] for b in bufs]), dtype=torch.float32, device=DEV)
        last = torch.as_tensor(np.stack([b["last"] for b in bufs]), dtype=torch.float32, device=DEV)

        with torch.no_grad():
            v_all = val(obs)
            v_last = val(last)
            adv = torch.zeros_like(rew)
            ret = torch.zeros_like(rew)
            for i in range(W):
                st = i * T
                v = v_all[st:st + T].cpu().numpy()
                nxt = float(v_last[i])
                gae = 0.0
                a = np.zeros(T, dtype=np.float32)
                for t in range(T - 1, -1, -1):
                    nt = 1.0 - float(done[st + t])
                    delta = float(rew[st + t]) + args.gamma * nxt * nt - float(v[t])
                    gae = delta + args.gamma * args.lam * nt * gae
                    a[t] = gae
                    nxt = float(v[t])
                adv[st:st + T] = torch.as_tensor(a, device=DEV)
                ret[st:st + T] = adv[st:st + T] + v_all[st:st + T]

        # ?"?reset ?"
        # KL ?lr=1e-7  KL>1 ?
        Dn = done.cpu().numpy()
        es = np.zeros(W * T, dtype=np.int64)
        idx = []
        for i in range(W):
            base = i * T
            a = 0
            for t in range(T + 1):
                if t == T or Dn[base + t] > 0.5:
                    for j in range(a, t):          # 
                        es[base + j] = base + a
                    s0 = a
                    while s0 + L <= t:             # 
                        idx.append(base + s0)
                        s0 += L
                    a = t + 1
        rng = np.random.default_rng(it)
        n_upd, kl_hist = 0, []
        stop = False
        for _ep in range(args.epochs):
            rng.shuffle(idx)
            for b0 in range(0, len(idx), args.minibatch):
                batch = idx[b0:b0 + args.minibatch]
                B = len(batch)
                mb_obs = torch.stack([obs[s:s + L] for s in batch])
                mb_act = torch.stack([act[s:s + L] for s in batch])
                mb_old = torch.stack([logp[s:s + L] for s in batch])
                mb_adv = torch.stack([adv[s:s + L] for s in batch])
                mb_ret = torch.stack([ret[s:s + L] for s in batch])
                mb_adv = (mb_adv - mb_adv.mean()) / (mb_adv.std() + 1e-8)
                h0 = torch.zeros(1, B, NHID, dtype=torch.float32, device=DEV)
                c0 = torch.zeros(1, B, NHID, dtype=torch.float32, device=DEV)
                with torch.no_grad():
                    z = torch.zeros(1, 1, NHID, dtype=torch.float32, device=DEV)
                    for j, s in enumerate(batch):
                        a0 = max(int(es[s]), s - args.burn)
                        if s > a0:
                            _, (hj, cj) = actor.memory(obs[a0:s].unsqueeze(1), (z, z))
                            h0[0, j] = hj[0, 0]
                            c0[0, j] = cj[0, 0]
                actor.train()
                mu = actor.seq(mb_obs, h0, c0)
                sd_ = logstd().clamp(1e-3, 2.0)
                newlp = (-0.5 * ((mb_act - mu) / sd_) ** 2 - torch.log(sd_)
                         - 0.5 * np.log(2 * np.pi)).sum(-1)
                kl = float(((mb_old - newlp) / E.NUM_ACT).mean().detach())
                if os.environ.get("G1PPO_DEBUG") and b0 == 0 and _ep == 0:
                    with torch.no_grad():
                        dm = (mb_act - mu).abs()
                        print("   dbg it=%d std=%.4f  mu-max=%.3f  |a-mu| mean=%.3f  "
                              "logp mean=%.2f  newlp mean=%.2f  kl=%.3f"
                              % (it, float(sd_.mean()), float(mu.abs().max()), float(dm.mean()),
                                 float(mb_old.mean()), float(newlp.mean()), kl), flush=True)
                kl_hist.append(kl)
                if kl > 6.0 * args.kl_target:
                    stop = True
                    break
                ratio = (newlp - mb_old).exp()
                s1 = ratio * mb_adv
                s2 = ratio.clamp(1 - args.clip, 1 + args.clip) * mb_adv
                loss_a = -torch.min(s1, s2).mean()
                if ref_actor is not None:
                    with torch.no_grad():
                        mu_ref = ref_actor.seq(mb_obs, h0, c0)
                    loss_a = loss_a + args.anchor * ((mu - mu_ref) ** 2).mean()
                v = val(mb_obs.reshape(B * L, -1)).reshape(B, L)
                loss_v = 0.5 * ((v - mb_ret) ** 2).mean()
                opt_a.zero_grad()
                opt_v.zero_grad()
                opt_s.zero_grad()
                (loss_a + loss_v).backward()
                torch.nn.utils.clip_grad_norm_(actor.parameters(), 1.0)
                torch.nn.utils.clip_grad_norm_(val.parameters(), 1.0)
                opt_a.step()
                opt_v.step()
                opt_s.step()
                actor.eval()
                n_upd += 1
            if stop:
                break

        # ?KL ?RNN 
        kl_now = float(np.mean(kl_hist)) if kl_hist else 0.0
        reverted = 0
        tgt = args.kl_target
        if kl_now > 3.0 * tgt:                 # ?
            actor.load_state_dict({k: v.to(DEV) for k, v in prev_sd.items()})
            for g in opt_a.param_groups:
                g["lr"] = max(g["lr"] * 0.5, 1e-7)
            for g in opt_s.param_groups:
                g["lr"] = max(g["lr"] * 0.5, 1e-7)
            reverted = 1
        elif kl_now < 0.5 * tgt:               # 
            for g in opt_a.param_groups:
                g["lr"] = min(g["lr"] * 1.5, args.lr_max)
            for g in opt_s.param_groups:
                g["lr"] = min(g["lr"] * 1.5, args.lr_max)
        nn_now = float(logstd().mean())

        rec = dict(it=it, slope_max=round(slope_max, 2),
                   rew=round(float(rew.mean()), 3), ep=int(sum(b["n_done"] for b in bufs)),
                   kl=round(kl_now, 4), std=round(nn_now, 3), upd=n_upd, revert=reverted,
                   lr=float(opt_a.param_groups[0]["lr"]),
                   mins=round((time.time() - t0) / 60.0, 1))
        log.append(rec)
        if it % 2 == 0 or it == 1:
            print("[%4d] slope<=%4.1f  rew=%7.3f  ep=%3d  kl=%+.4f  std=%.3f  upd=%d  rev=%d  "
                  "lr=%.1e  %.1f min"
                  % (it, rec["slope_max"], rec["rew"], rec["ep"], rec["kl"], rec["std"],
                     rec["upd"], rec["revert"], rec["lr"], rec["mins"]), flush=True)
        if args.eval_every and (it % args.eval_every == 0 or it == 1):
            ev_net = G1Actor()
            ev_net.load_state_dict({k: v.detach().cpu() for k, v in actor.state_dict().items()})
            ev_net.eval()
            score, det = ev.evaluate(ev_net, secs=5.0)
            if score > getattr(main, "_best", -1.0):
                main._best = score
                torch.save(ev_net.state_dict(), args.out + "_best.pt")
                print("        new best %.3f -> %s_best.pt" % (score, args.out), flush=True)
            rec["eval"] = round(score, 4)
            rec["eval_det"] = {str(k): v for k, v in det.items()}
            print("        eval %.3f  (" % score
                  + "  ".join("%.0f deg=%.2f" % (k, v) for k, v in det.items()) + ")", flush=True)
        if it % args.save_every == 0 or it == args.iters:
            torch.save(actor.state_dict(), args.out + ".pt")
            with open(args.out + ".json", "w", encoding="utf-8") as f:
                json.dump(log, f, ensure_ascii=False, indent=1)

    pool.shutdown(wait=True)
    torch.save(actor.state_dict(), args.out + ".pt")
    with open(args.out + ".json", "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    print("done -> %s.pt" % args.out)


if __name__ == "__main__":
    main()
