r"""把场景里的机器人按 hfield 真实高度落位（射线会被树/石头挡住，所以直接采样高度图）。

    python fix_robot_z.py --xml ../demo_v29.xml
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from polish import terrain_fn  # noqa: E402

STAND = {"go2_base": 0.27, "pelvis": 0.862}       # 站立时机身离地高度


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=os.path.join(os.path.dirname(HERE), "demo_v29.xml"))
    args = ap.parse_args()

    xml = open(args.xml, encoding="utf-8").read()
    tz = terrain_fn(args.xml)
    for name, stand in STAND.items():
        m = re.search(rf'<body name="{name}"[^>]*?pos="([-\d.]+) ([-\d.]+) ([-\d.]+)"', xml)
        if not m:
            print(f"  {name}: 找不到")
            continue
        x, y = float(m.group(1)), float(m.group(2))
        g = tz(x, y)
        if g is None:
            print(f"  {name}: 采样失败")
            continue
        z = g + stand
        xml = re.sub(rf'(<body name="{name}"[^>]*?pos="[-\d.]+ [-\d.]+ )([-\d.]+)(")',
                     lambda mm: f"{mm.group(1)}{z:.3f}{mm.group(3)}", xml, count=1)
        print(f"  {name}: ({x:.1f},{y:.1f}) 地形 z={g:.3f} → 机身 z={z:.3f}")
    open(args.xml, "w", encoding="utf-8").write(xml)
    print("已写回", os.path.basename(args.xml))


if __name__ == "__main__":
    main()
