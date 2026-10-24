r"""三档院子的"能不能站稳"自检：静置 2 秒，记录 Go2 机身高度变化。

    python check_yard.py                 # 平地 + 地形上各测一次
    python check_yard.py --tiers flat

判据：Go2 站立高度 0.27 m
    drift = |z(2s) - z(0.2s)| < 0.02 m → 稳定
    0.20 ~ 0.35 m                       → 高度正常（没趴、没飞）
"""
import argparse
import os

import mujoco
import numpy as np

ASSETS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DT = 0.002
STAND = 0.27

# 每档除了出生点，再在"地形上"探一次（这才是能不能通过的指标）
PROBE = {
    "flat": [(0.0, 0.0, "平地"), (5.0, -6.0, "同一片空地")],
    "stairs": [(0.0, 0.0, "平地"), (-9.0, 2.0, "台阶前")],
    "full": [(0.0, 0.0, "平地"), (5.0, -6.0, "碎石阵"), (5.0, 4.0, "Perlin 起伏")],
}


def ground_z(m, d, x, y, exclude):
    gid = np.array([-1], dtype=np.int32)
    dist = mujoco.mj_ray(m, d, np.array([x, y, 300.0]), np.array([0.0, 0.0, -1.0]),
                         None, 1, exclude, gid)
    return None if dist < 0 else 300.0 - dist


def run(path, x, y, seconds=2.0):
    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    if m.nkey > 0:
        mujoco.mj_resetDataKeyframe(m, d, 0)
    bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
    mujoco.mj_forward(m, d)

    gz = ground_z(m, d, x, y, bid)
    if gz is None:
        return None
    # freejoint 的前 3 个 qpos 就是机身位置
    d.qpos[0], d.qpos[1], d.qpos[2] = x, y, gz + STAND
    mujoco.mj_forward(m, d)

    zs = []
    for i in range(int(seconds / DT)):
        mujoco.mj_step(m, d)
        if (i + 1) % 100 == 0:
            zs.append(float(d.xpos[bid][2]))
    return {"ground": gz, "zs": zs, "z_end": zs[-1],
            "drift": abs(zs[-1] - zs[0]), "range": max(zs) - min(zs),
            "nq": m.nq, "ngeom": m.ngeom}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", default="flat,stairs,full")
    args = ap.parse_args()

    print(f"{'tier':<8}{'位置':<12}{'地形z':>8}{'0.2s':>8}{'1s':>8}{'2s':>8}"
          f"{'drift':>8}{'range':>8}{'h离地':>8}  判定")
    for tier in args.tiers.split(","):
        p = os.path.join(ASSETS, f"yard_{tier}.xml")
        if not os.path.exists(p):
            print(f"{tier:<8} 缺失 yard_{tier}.xml")
            continue
        for x, y, label in PROBE.get(tier, [(0.0, 0.0, "平地")]):
            r = run(p, x, y)
            if r is None:
                print(f"{tier:<8}{label:<12} 射线打不到地形")
                continue
            stable = r["drift"] < 0.02
            # 关键：站立高度要相对"脚下地面"算，不能看绝对 z（Perlin 山头本来就高）
            height = r["z_end"] - r["ground"]
            height_ok = 0.20 <= height <= 0.35
            verdict = "OK" if (stable and height_ok) else (
                "WARN 高度异常" if not height_ok else "WARN 还在晃")
            print(f"{tier:<8}{label:<12}{r['ground']:>8.3f}{r['zs'][0]:>8.3f}"
                  f"{r['zs'][len(r['zs']) // 2]:>8.3f}{r['z_end']:>8.3f}"
                  f"{r['drift']:>8.3f}{r['range']:>8.3f}"
                  f"{height:>8.3f}  {verdict}")


if __name__ == "__main__":
    main()
