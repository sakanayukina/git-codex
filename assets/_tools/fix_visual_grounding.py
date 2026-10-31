"""Snap selected visual bodies to the terrain using their world-space AABB.

Buildings with intentional underground geometry, roof slabs and loose debris
should stay out of the default target list unless explicitly requested.
"""
import argparse
import os
import re
import sys

import mujoco
import numpy as np

from polish import terrain_fn
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "train"))
import terrain_road


DEFAULT_BODIES = (
    "H7",
    "rock_moss_set_01_1",
    "boulder_01_2",
    "boulder_01_8",
)
ROCK_KEYS = ("rock", "boulder", "slab", "stone", "stump", "rk_", "seam_")


def body_world_aabb(model, data, body_id):
    transform = data.xmat[body_id].reshape(3, 3)
    origin = data.xpos[body_id]
    points = []
    for geom_id in range(model.ngeom):
        if int(model.geom_bodyid[geom_id]) != body_id:
            continue
        if model.geom_type[geom_id] in (
                mujoco.mjtGeom.mjGEOM_HFIELD,
                mujoco.mjtGeom.mjGEOM_PLANE):
            continue
        lo = model.geom_aabb[geom_id, :3]
        hi = model.geom_aabb[geom_id, 3:]
        for x in (lo[0], hi[0]):
            for y in (lo[1], hi[1]):
                for z in (lo[2], hi[2]):
                    points.append(transform @ np.array([x, y, z]) + origin)
    if not points:
        raise RuntimeError("body has no bounded geometry")
    return np.asarray(points)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml", required=True)
    parser.add_argument("--out", help="output XML; defaults to in-place")
    parser.add_argument("--bodies", nargs="+", default=list(DEFAULT_BODIES))
    parser.add_argument("--skip-grounding", action="store_true",
                        help="skip AABB grounding; apply --shift operations only")
    parser.add_argument("--shift", nargs="*", default=[],
                        metavar="BODY=DELTA",
                        help="optional manual z shifts, e.g. H2=-0.18")
    parser.add_argument("--clearance", type=float, default=0.03,
                        help="positive embeds the lowest point by this much")
    parser.add_argument("--terrain", choices=("auto", "road", "png"),
                        default="auto",
                        help="height source; auto prefers terrain/hf_road.npz")
    parser.add_argument("--auto-rocks", action="store_true",
                        help="find and ground every floating static rock/stump")
    parser.add_argument("--rock-threshold", type=float, default=0.08)
    args = parser.parse_args()
    out = args.out or args.xml

    use_road = (args.terrain == "road"
                or (args.terrain == "auto" and os.path.exists(terrain_road.NPZ)))
    model = (terrain_road.load_model(args.xml)
             if use_road else mujoco.MjModel.from_xml_path(args.xml))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    if use_road:
        ground = lambda x, y: terrain_road.ray_height(model, data, x, y)
    else:
        ground = terrain_fn(args.xml)
    xml = open(args.xml, encoding="utf-8").read()

    bodies = list(args.bodies)
    if args.auto_rocks:
        dynamic = {
            int(model.jnt_bodyid[j]) for j in range(model.njnt)
            if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE
        }
        bodies = []
        for body_id in range(1, model.nbody):
            if body_id in dynamic:
                continue
            name = mujoco.mj_id2name(
                model, mujoco.mjtObj.mjOBJ_BODY, body_id) or ""
            if not any(key in name.lower() for key in ROCK_KEYS):
                continue
            try:
                points = body_world_aabb(model, data, body_id)
            except RuntimeError:
                continue
            heights = []
            for x in np.linspace(points[:, 0].min(), points[:, 0].max(), 7):
                for y in np.linspace(points[:, 1].min(), points[:, 1].max(), 7):
                    height = ground(float(x), float(y))
                    if height is not None and np.isfinite(height):
                        heights.append(float(height))
            if heights and float(points[:, 2].min()) - max(heights) > args.rock_threshold:
                bodies.append(name)
        print("auto rocks:", len(bodies))

    for name in ([] if args.skip_grounding else bodies):
        body_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, name)
        if body_id < 0:
            raise SystemExit("unknown body: " + name)
        points = body_world_aabb(model, data, body_id)
        min_z = float(points[:, 2].min())
        xmin, xmax = float(points[:, 0].min()), float(points[:, 0].max())
        ymin, ymax = float(points[:, 1].min()), float(points[:, 1].max())
        heights = []
        for x in np.linspace(xmin, xmax, 7):
            for y in np.linspace(ymin, ymax, 7):
                height = ground(float(x), float(y))
                if height is not None and np.isfinite(height):
                    heights.append(float(height))
        if not heights:
            raise SystemExit("no terrain under body: " + name)
        target_min_z = max(heights) - args.clearance
        delta = target_min_z - min_z
        pattern = re.compile(
            r'(<body\b[^>]*\bname="' + re.escape(name) +
            r'"[^>]*\bpos="[-\d.]+ [-\d.]+ )([-\d.]+)(")')
        xml, count = pattern.subn(
            lambda match: match.group(1) +
            f"{float(match.group(2)) + delta:.3f}" + match.group(3),
            xml, count=1)
        if count != 1:
            raise SystemExit("could not rewrite body z: " + name)
        print("%-26s z %+.3f -> %+.3f" %
              (name, float(model.body_pos[body_id][2]),
               float(model.body_pos[body_id][2]) + delta))

    for spec in args.shift:
        if "=" not in spec:
            raise SystemExit("invalid --shift: " + spec)
        name, raw_delta = spec.rsplit("=", 1)
        delta = float(raw_delta)
        pattern = re.compile(
            r'(<body\b[^>]*\bname="' + re.escape(name) +
            r'"[^>]*\bpos="[-\d.]+ [-\d.]+ )([-\d.]+)(")')
        xml, count = pattern.subn(
            lambda match: match.group(1) +
            f"{float(match.group(2)) + delta:.3f}" + match.group(3),
            xml, count=1)
        if count != 1:
            raise SystemExit("could not shift body: " + name)
        print("%-26s manual z %+.3f" % (name, delta))

    with open(out, "w", encoding="utf-8") as handle:
        handle.write(xml)
    print("wrote", out)


if __name__ == "__main__":
    main()
