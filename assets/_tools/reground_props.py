# Re-seat static props (trees/rocks/grass) on the current terrain after a
# heightfield change. Buildings are handled separately by fix_grounding.py.
import argparse
import os
import re

import mujoco
import numpy as np

PREFIXES = (
    "tree", "maple", "rock", "rk_", "grass", "bush",
    "stump", "tyre", "barrier", "car", "debris",
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    args = ap.parse_args()

    xml = open(args.src, encoding="utf-8").read()
    m = mujoco.MjModel.from_xml_path(args.src)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    gg = np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8)

    changed = 0
    for i in range(m.nbody):
        name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i)
        if not name:
            continue
        low = name.lower()
        if not any(low.startswith(p) for p in PREFIXES):
            continue
        pos = d.xpos[i]
        gid = np.zeros(1, dtype=np.int32)
        dist = mujoco.mj_ray(
            m, d, np.array([pos[0], pos[1], 400.0]), np.array([0.0, 0.0, -1.0]),
            gg, 1, i, gid,
        )
        if dist < 0:
            continue
        ground = 400.0 - dist
        pat = re.compile(
            r'(<body name="' + re.escape(name) + r'"[^>]*?pos="[-\d.]+ [-\d.]+ )([-\d.]+)(")'
        )
        xml, n = pat.subn(lambda mm: mm.group(1) + f"{ground:.3f}" + mm.group(3), xml, count=1)
        changed += n

    with open(args.dst, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"regrounded {changed} props -> {args.dst}")


if __name__ == "__main__":
    main()
