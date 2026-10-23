# Re-seat every building on the terrain using MuJoCo's own hfield surface.
# Usage: python fix_grounding.py --in demo_v7.xml --out demo_v8.xml
import argparse
import glob
import json
import os
import re

import mujoco
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def obj_min_z(path):
    lo = 1e9
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                lo = min(lo, float(line.split()[3]))
    return 0.0 if lo > 1e8 else lo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ASSETS, "demo_v7.xml"))
    ap.add_argument("--out", dest="dst", default=os.path.join(ASSETS, "demo_v9.xml"))
    ap.add_argument("--config", default=os.path.join(ASSETS, "buildings.json"))
    ap.add_argument("--sink", type=float, default=0.05)
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    xml = open(args.src, encoding="utf-8").read()
    model = mujoco.MjModel.from_xml_path(args.src)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    geomgroup = np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8)

    def ground_z(x, y, body_id):
        geomid = np.zeros(1, dtype=np.int32)
        dist = mujoco.mj_ray(
            model, data, np.array([x, y, 300.0]), np.array([0.0, 0.0, -1.0]),
            geomgroup, 1, body_id, geomid,
        )
        return None if dist < 0 else 300.0 - dist

    for p in cfg["plots"]:
        bid = p["id"]
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, bid)
        W, D = p["size"][0] / 2.0, p["size"][1] / 2.0
        pts = [(p["x"] + dx, p["y"] + dy)
               for dx in (-W, 0.0, W) for dy in (-D, 0.0, D)]
        gs = [ground_z(x, y, body_id) for x, y in pts]
        gs = [g for g in gs if g is not None]
        if not gs:
            print(f"{bid}: no ground hit, skipped")
            continue
        platform_top = max(gs)
        platform_bottom = min(gs) - 0.8
        depth = platform_top - platform_bottom
        rel = (p.get("model") or "").strip()
        min_z = 0.0
        if rel:
            objs = glob.glob(os.path.join(ASSETS, rel, "*.obj"))
            if objs:
                min_z = min(obj_min_z(f) for f in objs)
        new_z = platform_top - min_z * float(p.get("model_scale") or 1.0)
        pattern = re.compile(
            r'(<body name="' + re.escape(bid) + r'"[^>]*?pos="[-\d.]+ [-\d.]+ )([-\d.]+)(")'
        )
        xml, n = pattern.subn(lambda m: m.group(1) + f"{new_z:.3f}" + m.group(3), xml, count=1)
        if depth > 0.3:
            platform = (
                f'<geom type="box" size="{W + 0.6:.2f} {D + 0.6:.2f} {depth / 2:.2f}" '
                f'pos="0 0 {min_z - depth / 2:.2f}" material="dirt" '
                f'group="1" contype="1" conaffinity="1"/>'
            )
            body_pat = re.compile(r'(<body name="' + re.escape(bid) + r'"[^>]*>)')
            xml = body_pat.sub(lambda m: m.group(1) + platform, xml, count=1)
        print(f"{bid}: ground {min(gs):.2f}..{max(gs):.2f} platform_depth={depth:.2f} "
              f"min_z={min_z:.2f} -> body_z={new_z:.2f}")

    with open(args.dst, "w", encoding="utf-8") as f:
        f.write(xml)
    print("wrote", args.dst)


if __name__ == "__main__":
    main()
