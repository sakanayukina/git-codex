r"""Compose a MuJoCo rescue scene: real DEM heightfield + Poly Haven props + rubble pile.

Reads the converted OBJ/PNG props under assets/props, samples the terrain heightfield
so everything sits on the ground, and writes one self-contained MJCF file.

    python build_scene.py --out ..\demo_rescue_scene.xml
"""
import argparse
import glob
import math
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def find(rel):
    """Locate a converted prop: assets/props/<group>/<id>/<id>_1k.obj"""
    obj = glob.glob(os.path.join(ASSETS, "props", rel, "*_1k.obj"))
    if not obj:
        return None
    obj = obj[0]
    png = obj.replace("_1k.obj", "_1k_diffuse.png")
    return obj, (png if os.path.exists(png) else None)


class Terrain:
    def __init__(self, png, extent, relief, base=0.01):
        g = np.asarray(Image.open(png).convert("L"), dtype=np.float64)
        self.z = g / 255.0 * relief
        self.nrow, self.ncol = self.z.shape
        self.extent, self.relief, self.base = extent, relief, base

    def height(self, x, y):
        fx = (x + self.extent / 2) / self.extent * (self.ncol - 1)
        fy = (self.extent / 2 - y) / self.extent * (self.nrow - 1)  # PNG row 0 = +Y
        x0, y0 = int(np.floor(fx)), int(np.floor(fy))
        x1, y1 = min(x0 + 1, self.ncol - 1), min(y0 + 1, self.nrow - 1)
        dx, dy = fx - x0, fy - y0
        z = self.z
        v = (z[y0, x0] * (1 - dx) * (1 - dy) + z[y0, x1] * dx * (1 - dy)
             + z[y1, x0] * (1 - dx) * dy + z[y1, x1] * dx * dy)
        return self.base + v

    def slope(self, x, y, eps=2.0):
        return math.hypot(self.height(x + eps, y) - self.height(x - eps, y),
                          self.height(x, y + eps) - self.height(x, y - eps)) / (2 * eps)


def obj_bbox(path):
    """Bounding box of an OBJ (cached): needed to sit meshes exactly on the ground."""
    with open(path, "r", encoding="utf-8") as f:
        pts = [[float(x) for x in ln.split()[1:4]] for ln in f if ln.startswith("v ")]
    a = np.asarray(pts)
    return a.min(0), a.max(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--terrain", default="terrain/dem_wenchuan_200m.png")
    ap.add_argument("--extent", type=float, default=200.0)
    ap.add_argument("--relief", type=float, default=66.5)
    ap.add_argument("--out", default="demo_rescue_scene.xml")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-rubble", action="store_true")
    ap.add_argument("--ground-tex", default="leafy_grass")
    args = ap.parse_args()

    t = Terrain(os.path.join(ASSETS, args.terrain), args.extent, args.relief)
    rng = np.random.default_rng(args.seed)
    rel = lambda p: os.path.relpath(p, ASSETS).replace(os.sep, "/")

    assets, bodies, meshes = [], [], {}

    def mesh_of(relpath, scale=None):
        key = (relpath, scale)
        if key in meshes:
            return meshes[key]
        name = f"m{len(meshes)}"
        s = f' scale="{scale} {scale} {scale}"' if scale and scale != 1.0 else ""
        assets.append(f'<mesh name="{name}" file="{relpath}"{s}/>')
        meshes[key] = name
        return name

    def texture_of(png_rel, name=None):
        name = name or f"t{len([a for a in assets if a.startswith('<texture')])}"
        assets.append(f'<texture name="{name}" type="2d" file="{png_rel}"/>')
        assets.append(f'<material name="{name}_mat" texture="{name}"/>')
        return f"{name}_mat"

    # ---------------------------------------------------------------- props
    prop_specs = {
        "rocks": [
            ("rock_moss_set_01", 0.55, 6), ("boulder_01", 1.0, 10), ("rock_07", 6.0, 14),
        ],
        "debris": [
            ("tree_stump_01", 1.0, 5), ("bark_debris_01", 1.0, 8),
        ],
        "ground": [
            ("grass_medium_01", 1.0, 45),
            ("moss_01", 1.0, 30),
        ],
        "vehicles": [
            ("covered_car", 1.0, 2), ("concrete_road_barrier", 1.0, 4), ("old_tyre", 1.0, 6),
        ],
    }

    half = args.extent / 2 - 12
    cx, cy = (10.0, -6.0) if not args.no_rubble else (0.0, 0.0)
    placed = []

    def spread(n, min_sep=3.0, max_slope=1.2, zmin=None):
        got = []
        for _ in range(n * 40):
            if len(got) >= n:
                break
            x, y = rng.uniform(-half, half, 2)
            if t.slope(x, y) > max_slope:
                continue
            if any((x - a) ** 2 + (y - b) ** 2 < min_sep ** 2 for a, b in got):
                continue
            got.append((float(x), float(y)))
        return got

    def camera(name, eye, target):
        pos = np.array(eye, dtype=float)
        d = np.array(target, dtype=float) - pos
        d /= np.linalg.norm(d)
        right = np.cross(d, [0.0, 0.0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, d)
        ax = " ".join(f"{v:.5f}" for v in [*right, *up])
        return (f'<camera name="{name}" pos="{pos[0]:.2f} {pos[1]:.2f} {pos[2]:.2f}" '
                f'xyaxes="{ax}"/>')

    def conifer(x, y, h, tint):
        """Procedural conifer: a photogrammetry tree decimated to MuJoCo size is a blob."""
        z = t.height(x, y)
        bark = np.array([0.28, 0.20, 0.13]) * rng.uniform(0.88, 1.15)
        p = [f'<body name="tree_{len(placed)}" pos="{x:.2f} {y:.2f} {z:.3f}" '
             f'euler="0 0 {rng.uniform(0, 360):.1f}">',
             f'<geom type="cylinder" size="{0.034 * h:.3f} {0.17 * h:.3f}" pos="0 0 {0.17 * h:.3f}" '
             f'rgba="{bark[0]:.3f} {bark[1]:.3f} {bark[2]:.3f} 1" friction="0.9 0.02 0.001"/>']
        # 多层扁椭球叠成层叠针叶冠：底层大而暗，顶层小而亮
        tiers = [
            (0.24, 0.24, 0.10, 0.70),
            (0.38, 0.19, 0.09, 0.82),
            (0.51, 0.14, 0.08, 0.95),
            (0.63, 0.09, 0.07, 1.10),
            (0.74, 0.05, 0.06, 1.20),
        ]
        for c, r, hr, br in tiers:
            g = np.clip(tint * rng.uniform(0.92, 1.08) * br, 0.0, 1.0)
            p.append(f'<geom type="ellipsoid" size="{r * h:.3f} {r * h:.3f} {hr * h:.3f}" '
                     f'pos="0 0 {c * h:.3f}" rgba="{g[0]:.3f} {g[1]:.3f} {g[2]:.3f} 1" '
                     f'contype="0" conaffinity="0" group="1"/>')
        p.append("</body>")
        placed.append((x, y))
        return "".join(p)

    for (x, y) in spread(16, min_sep=6.0, max_slope=1.5):
        bodies.append(conifer(x, y, rng.uniform(9.0, 19.0), np.array([0.10, 0.26, 0.11])))
    for (x, y) in spread(6, min_sep=3.0, max_slope=1.8):
        bodies.append(conifer(x, y, rng.uniform(2.0, 4.5), np.array([0.12, 0.30, 0.12])))

    # ------------------------------------------------------- hero props (fixed spots)
    def place(group, pid, x, y, yaw, scale=1.0):
        hit = find(os.path.join(group, pid))
        if not hit:
            return
        obj, png = hit
        mname = mesh_of(rel(obj), scale=scale)
        mat = texture_of(rel(png)) if png else None
        mat_attr = f' material="{mat}"' if mat else ' rgba="0.55 0.55 0.55 1"'
        lo, hi = obj_bbox(obj)
        cxm, cym = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
        bodies.append(
            f'<body name="{pid}_hero_{len(placed)}" '
            f'pos="{x - cxm * scale:.2f} {y - cym * scale:.2f} '
            f'{t.height(x, y) - lo[2] * scale:.3f}" euler="0 0 {yaw}">'
            f'<geom type="mesh" mesh="{mname}"{mat_attr} contype="0" conaffinity="0" group="1"/>'
            f'</body>')
        placed.append((x, y))

    place("vehicles", "covered_car", cx + 8.5, cy - 5.0, 25)
    place("vehicles", "concrete_road_barrier", cx - 9.0, cy - 2.0, 8)
    place("vehicles", "concrete_road_barrier", cx - 9.0, cy - 4.5, 4)
    place("vehicles", "old_tyre", cx + 4.0, cy - 7.5, 0)
    place("rocks", "boulder_01", cx - 7.0, cy + 6.0, 40)
    place("rocks", "rock_moss_set_01", cx + 9.0, cy + 7.0, 120, scale=0.45)
    place("debris", "tree_stump_01", cx + 3.0, cy + 7.5, 70)

    for group, items in prop_specs.items():
        for pid, scale, count in items:
            hit = find(os.path.join(group, pid))
            if not hit:
                print(f"  ! missing {group}/{pid}, skipped")
                continue
            obj, png = hit
            mname = mesh_of(rel(obj), scale=scale)
            mat = texture_of(rel(png)) if png else None
            mat_attr = f' material="{mat}"' if mat else ' rgba="0.55 0.55 0.55 1"'
            lo, hi = obj_bbox(obj)
            cx_, cy_, zmin = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]
            for i, (x, y) in enumerate(spread(count, min_sep=3.5, max_slope=1.6)):
                z = t.height(x, y) - zmin * scale
                yaw = rng.uniform(0, 360)
                bodies.append(
                    f'<body name="{pid}_{i}" pos="{x - cx_ * scale:.2f} {y - cy_ * scale:.2f} {z:.3f}" '
                    f'euler="0 0 {yaw:.1f}">'
                    f'<geom type="mesh" mesh="{mname}"'
                    f'{mat_attr} contype="0" conaffinity="0" group="1"/>'
                    f'</body>')
                placed.append((x, y))

    # ---------------------------------------------------------------- rubble
    if not args.no_rubble:
        cx, cy = 10.0, -6.0
        ground_z = t.height(cx, cy)

        # collapsed slabs: a leaning floor slab + two broken wall panels
        slabs = [
            (0.0, 0.0, 1.1, 4.2, 3.0, 0.16, 14, 0),
            (-3.2, 1.4, 0.9, 3.4, 2.6, 0.14, -62, 22),
            (2.9, 1.8, 1.0, 3.0, 2.2, 0.14, 48, -18),
        ]
        for i, (dx, dy, dz, sx, sy, sz, yaw, tilt) in enumerate(slabs):
            bodies.append(
                f'<body name="slab{i}" pos="{cx + dx:.2f} {cy + dy:.2f} {ground_z + dz:.3f}" '
                f'euler="{tilt} 0 {yaw}">'
                f'<freejoint/>'
                f'<geom type="box" size="{sx:.2f} {sy:.2f} {sz:.3f}" '
                f'rgba="0.70 0.68 0.64 1" density="2400" friction="0.9 0.02 0.001"/>'
                f'</body>')

        n = 90
        for i in range(n):
            r = 5.0 * math.sqrt(rng.uniform(0, 1))
            a = rng.uniform(0, 2 * math.pi)
            dx, dy = r * math.cos(a), r * math.sin(a)
            drop = 0.55 * (1 - (r / 5.0) ** 2)
            sx = rng.uniform(0.25, 0.62)
            sy = rng.uniform(0.25, 0.62)
            sz = rng.uniform(0.10, 0.28)
            bodies.append(
                f'<body name="chunk{i}" pos="{cx + dx:.2f} {cy + dy:.2f} '
                f'{ground_z + drop + sz:.3f}">'
                f'<freejoint/>'
                f'<geom type="box" size="{sx:.3f} {sy:.3f} {sz:.3f}" '
                f'rgba="0.62 0.60 0.57 1" density="2100" friction="1.2 0.02 0.001"/>'
                f'</body>')

    # ---------------------------------------------------------------- MJCF
    gz = t.height(cx, cy)
    cam_xml = (camera("wide", (cx - 42, cy - 58, gz + 34), (cx, cy, gz + 3))
               + camera("close", (cx - 7, cy - 12, gz + 3.5), (cx, cy, gz + 1.2)))

    xml = f"""<mujoco model="rescue_scene">
  <compiler angle="degree"/>
  <visual>
    <global offwidth="1280" offheight="720"/>
    <quality shadowsize="8192"/>
    <map fogstart="120" fogend="320"/>
    <headlight ambient="0.32 0.34 0.36" diffuse="0.5 0.5 0.5" specular="0.05 0.05 0.05"/>
  </visual>
  <statistic center="0 0 {args.relief / 2:.1f}" extent="{args.extent * 0.55:.1f}"/>
  <option timestep="0.002" gravity="0 0 -9.81" cone="elliptic" impratio="10"/>
  <asset>
    <texture name="sky" type="skybox" builtin="gradient" rgb1="0.30 0.42 0.58"
             rgb2="0.66 0.74 0.82" width="512" height="3072"/>
    <texture name="gtex" type="2d" file="tex/{args.ground_tex}_diffuse.png"/>
    <material name="gmat" texture="gtex" rgba="0.92 0.92 0.88 1" texrepeat="24 24" texuniform="true"
              specular="0.0" shininess="0.0"/>
    <hfield name="terrain" file="{rel(os.path.join(ASSETS, args.terrain))}"
            size="{args.extent / 2:.1f} {args.extent / 2:.1f} {args.relief:.2f} 0.01"/>
    {"".join(assets)}
  </asset>
  <worldbody>
    <light name="sun" pos="85 -35 150" dir="-0.5 0.25 -0.82" diffuse="1.0 0.87 0.70"
           specular="0.12 0.12 0.12" castshadow="true"/>
    <light name="fill" pos="-70 60 90" dir="0.55 -0.35 -0.75" diffuse="0.22 0.27 0.36"
           specular="0 0 0" castshadow="false"/>
    <light name="rim" pos="-90 -100 120" dir="0.45 0.6 -0.7" diffuse="0.30 0.34 0.42"
           specular="0.08 0.08 0.08" castshadow="false"/>
    <geom name="ground" type="hfield" hfield="terrain" material="gmat"
          friction="1.0 0.02 0.001"/>
    {cam_xml}
    {"".join(bodies)}
  </worldbody>
</mujoco>
"""
    out = os.path.join(ASSETS, args.out)
    with open(out, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"wrote {out}: {len(bodies)} bodies, {len(meshes)} meshes, {len(assets)} assets")


if __name__ == "__main__":
    main()
