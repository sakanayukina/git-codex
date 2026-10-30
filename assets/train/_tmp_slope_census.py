r"""统计地形坡度分布，看看有多少地面是 G1 能走的（≤2° / ≤4°）。"""
import argparse
import os

import numpy as np

import terrain_road

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", default=os.path.join(HERE, "..", "terrain", "hf_road.npz"))
    a = ap.parse_args()
    d = np.load(a.npz)
    z = d["data"].astype(np.float64) * float(d["elev"]) + float(d["base"])
    cell = float(d["cell"])
    gy, gx = np.gradient(z, cell)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    # 只统计 hfield 有效区域（npz 是整个 200×200 场地）
    print("%-12s %8s %8s" % ("区间", "占比", "面积 m2"))
    bins = [(0, 1, "≤1°"), (1, 2, "1–2°"), (2, 4, "2–4°"),
            (4, 8, "4–8°"), (8, 15, "8–15°"), (15, 90, ">15°")]
    total = slope.size
    for lo, hi, name in bins:
        m = (slope > lo) & (slope <= hi) if lo > 0 else (slope <= hi)
        print("%-12s %7.1f%% %8.0f" % (name, 100.0 * m.sum() / total, m.sum() * cell * cell))
    flat = slope <= 2.0
    print("≤2° 合计 %.1f%%（%.0f m2）" % (100.0 * flat.sum() / total, flat.sum() * cell * cell))

    # 最大连通平坦块（4 邻域，粗扫）
    try:
        from scipy import ndimage
        lab, n = ndimage.label(flat)
        sizes = ndimage.sum(flat, lab, range(1, n + 1))
        k = int(np.argmax(sizes)) + 1
        ys, xs = np.where(lab == k)
        radius = float(d["radius"])
        print("最大平坦连通块：%.0f m2，%.0f 格，中心 (%.1f, %.1f)"
              % (sizes[k - 1] * cell * cell, sizes[k - 1],
                 xs.mean() / (slope.shape[1] - 1) * 2 * radius - radius,
                 ys.mean() / (slope.shape[0] - 1) * 2 * radius - radius))
    except ImportError:
        print("（没装 scipy，跳过连通块统计）")


if __name__ == "__main__":
    main()
