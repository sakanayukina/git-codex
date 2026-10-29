"""能力包络阶梯：生成一系列「已知坡度」的 hfield 场景，用来测机器人的最大可行走坡度。

坡度定义：hfield 半宽 HALF（米），高度 hist，则坡角 = atan(hist / (2*HALF))。
坡面沿 +x 上升（PNG 列方向 = x），机器人朝 +x 走即为爬坡。

    python capability_ladder.py --out _ladder --half 10 --angles 3 5 8 10 12 15 20 25 30
"""
import argparse
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import env  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ladder"))
    ap.add_argument("--width", type=float, default=20.0, help="hfield 边长（米，make_xml 会除以 2 存 radius）")
    ap.add_argument("--angles", nargs="+", type=float,
                    default=[0, 3, 5, 8, 10, 12, 15, 20, 25, 30])
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    width = a.width
    rows, cols = 128, 128

    for ang in a.angles:
        flat_frac = 0.15
        ramp_len = width * (1.0 - flat_frac)          # 实际坡段长度（米）
        hist = ramp_len * math.tan(math.radians(ang))  # 让真实坡度 = 标称角度
        grad = np.zeros((rows, cols), dtype=np.float64)
        flat_cells = int(cols * flat_frac)
        grad[:, flat_cells:] = np.linspace(0.0, 1.0, cols - flat_cells)[None, :]

        png = os.path.join(a.out, "slope_%02d.png" % int(round(ang)))
        env.save_gray_png((grad * 255).astype(np.uint8), png)
        xml_text = env.make_xml(png, hfield_size=width, terrain_h=max(hist, 0.05))
        xml = os.path.join(a.out, "slope_%02d.xml" % int(round(ang)))
        open(xml, "w", encoding="utf-8").write(xml_text)
        print("角 %.0f°  落差 %.2f m  ->  %s" % (ang, hist, os.path.basename(xml)))

    print("\n生成完毕，目录:", a.out)


if __name__ == "__main__":
    main()
