r"""评测：在合成坡面上比较「官方 G1 策略」与「微调后的权重」的存活/位移。

    & "C:/Users/18967/anaconda3/envs/mujoco/python.exe" g1_eval.py                     # 只测官方
    & "C:/Users/18967/anaconda3/envs/mujoco/python.exe" g1_eval.py --ckpt ckpt/g1_slope_ppo.pt

口径
----
- 每个 (坡度, 行走方向) 组合跑 `--secs` 秒（默认 6 s），指令 vx=0.5，地形光滑（rough=0）。
- `up` 是机身 z 轴与世界 z 的夹角余弦，<0.55 判摔；`dist` 是水平位移。
- 行走方向：`up`=上坡、`down`=下坡、`side`=横坡（左右各一次，取成功率平均）。
"""
import argparse
import os

import numpy as np
import torch

import g1_env as E
from g1_policy_net import G1Actor

HERE = os.path.dirname(os.path.abspath(__file__))


def run_case(actor, slope, heading, secs=6.0, vx=0.5, seed=0):
    env = E.G1SlopeEnv(seed=seed)
    obs = env.reset(slope_deg=slope, direction=0.0, rough=0.0, cmd=(vx, 0.0),
                    yaw=heading, seed=seed + 1)
    h = c = None
    n = int(secs / (E.DECIM * E.DT))
    fell_at = None
    for t in range(n):
        with torch.no_grad():
            mu_t, h, c = actor.step(torch.from_numpy(obs).unsqueeze(0), h, c)
        obs, rew, done, info = env.step(mu_t.numpy().flatten())
        if done:
            fell_at = t
            break
    p = np.array(env.d.qpos[0:2], dtype=float)          # 起点在原点
    return dict(ok=fell_at is None, t_steps=(fell_at if fell_at is not None else n),
                dist=float(np.linalg.norm(p)), up=float(info["up"]))


SLOPES = (4.0, 6.0, 8.0, 10.0)
HEADINGS = (("up", 0.0), ("down", np.pi), ("side", np.pi / 2))


def evaluate(actor, slopes=SLOPES, secs=5.0, vx=0.5, seed0=7):
    """返回 (总分, {坡度: 成功率})，供训练时当验证指标。"""
    out, tot = {}, 0.0
    for k, s in enumerate(slopes):
        ok = 0
        for j, (_, hd) in enumerate(HEADINGS):
            r = run_case(actor, s, hd, secs, vx, seed=seed0 + 10 * k + j)
            ok += 1 if r["ok"] else 0
        rate = ok / float(len(HEADINGS))
        out[s] = rate
        tot += rate
    return tot / max(1, len(slopes)), out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="")
    ap.add_argument("--slopes", default="0,3,5,6,7,8,10,12")
    ap.add_argument("--secs", type=float, default=5.0)
    ap.add_argument("--vx", type=float, default=0.5)
    args = ap.parse_args()

    actor = G1Actor.from_official()
    tag = "official"
    if args.ckpt and os.path.exists(args.ckpt):
        actor.load_state_dict(torch.load(args.ckpt, map_location="cpu"))
        tag = os.path.basename(args.ckpt)
    actor.eval()

    print("== %s  (vx=%.2f, %.0f s/回合)" % (tag, args.vx, args.secs))
    print("%6s %8s %8s %8s %8s %8s" % ("slope", "up_ok", "down_ok", "side_ok", "up_dist", "best_up"))
    tot = 0.0
    for s in [float(x) for x in args.slopes.split(",")]:
        res = {}
        for name, heading in (("up", 0.0), ("down", np.pi), ("side_l", np.pi / 2), ("side_r", -np.pi / 2)):
            res[name] = run_case(actor, s, heading, args.secs, args.vx, seed=int(s * 10) + 3)
        side_ok = 0.5 * (res["side_l"]["ok"] + res["side_r"]["ok"])
        tot += (res["up"]["ok"] + res["down"]["ok"] + side_ok) / 3.0
        print("%6.1f %8s %8s %8.2f %8.2f %8.2f"
              % (s, "OK" if res["up"]["ok"] else "fall@%.1f" % (res["up"]["t_steps"] * E.DECIM * E.DT),
                 "OK" if res["down"]["ok"] else "fall@%.1f" % (res["down"]["t_steps"] * E.DECIM * E.DT),
                 side_ok, res["up"]["dist"],
                 min(res[k]["up"] for k in res)), flush=True)
    print("综合成功率 %.3f" % (tot / max(1, len(args.slopes.split(",")))))


if __name__ == "__main__":
    main()
