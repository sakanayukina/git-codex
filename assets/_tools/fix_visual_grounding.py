"""Snap selected visual bodies to the terrain using their world-space AABB.

Buildings with intentional underground geometry, roof slabs and loose debris
should stay out of the default target list unless explicitly requested.
"""
import argparse
import os
import re

import mujoco
import numpy as np

from polish import terrain_fn


DEFAULT_BODIES = (
    "H7",
    "rock_moss_set_01_1",
    "boulder_01_2",
    "boulder_01_8",
)


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
    parser.add_argument("--clearance", type=float, default=0.03,
                        help="positive embeds the lowest point by this much")
    args = parser.parse_args()
    out = args.out or args.xml

    model = mujoco.MjModel.from_xml_path(args.xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    ground = terrain_fn(args.xml)
    xml = open(args.xml, encoding="utf-8").read()

    for name in args.bodies:
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
                if height is not None:
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

    with open(out, "w", encoding="utf-8") as handle:
        handle.write(xml)
    print("wrote", out)


if __name__ == "__main__":
    main()
