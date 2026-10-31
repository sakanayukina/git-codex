r"""测 G1 仿真的吞吐，给 PPO 训练估预算。

    python bench_sim.py                 # 单线程 / 线程池 / mujoco.rollout 三种口径
    python bench_sim.py --envs 64

结论默认打在 stdout。
"""
import argparse
import os
import time

import mujoco
import mujoco.rollout as ro
import numpy as np

import terrain_road

HERE = os.path.dirname(os.path.abspath(__file__))
XML = os.path.join(HERE, "..", "g1_village_final.xml")


def make(n, xml):
    m = terrain_road.load_model(xml)
    ds = []
    for _ in range(n):
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        d.qpos[0:3] = [0.0, 0.0, 0.8]
        mujoco.mj_forward(m, d)
        ds.append(d)
    return m, ds


def bench_serial(n, decim=10, blocks=20):
    m, ds = make(n, XML)
    t0 = time.time()
    for _ in range(blocks):
        for d in ds:
            for _ in range(decim):
                d.ctrl[:] = 0.0
                mujoco.mj_step(m, d)
    el = time.time() - t0
    return n * blocks * decim / el


def bench_rollout_loop(n, decim=10, blocks=20):
    """每块一次 rollout 调用（控制写死 0），看线程池的真实吞吐。"""
    m, ds = make(n, XML)
    ctrl = np.zeros((n, decim, m.nu))
    t0 = time.time()
    for _ in range(blocks):
        ro.rollout(m, ds, control=ctrl, nstep=decim)
    el = time.time() - t0
    return n * blocks * decim / el


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--envs", type=int, default=32)
    a = ap.parse_args()
    n = a.envs
    print("envs = %d" % n)
    s = bench_serial(n)
    print("serial          : %8.0f physics steps/s" % s)
    r = bench_rollout_loop(n)
    print("mujoco.rollout  : %8.0f physics steps/s" % r)
    print("=> 控制步(=10 物理步) 每秒: serial %.0f / rollout %.0f"
          % (s / 10, r / 10))


if __name__ == "__main__":
    main()
