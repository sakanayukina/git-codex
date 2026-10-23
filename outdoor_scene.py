import os
import struct
import sys
import zlib

import mujoco
import mujoco.viewer
import numpy as np


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TERRAIN_PNG = os.path.join(BASE_DIR, "terrain.png").replace("\\", "/")
SCENE_XML = os.path.join(BASE_DIR, "assets", "demo_v26.xml")
H_MAX = 1.8
N_GRID = 120


def terrain_height(x, y):
    h = 0.7 * np.clip((-x + 8.0) / 16.0, 0.0, 1.0)
    h += 0.30 * np.sin(0.35 * x + 0.5) * np.cos(0.30 * y + 0.2)
    h += 0.20 * np.sin(0.75 * x + 1.3) * np.cos(0.65 * y + 0.8)
    h += 0.12 * np.sin(1.60 * x + 0.2) * np.cos(1.40 * y + 1.9)
    h += 0.06 * np.sin(3.10 * x + 2.1) * np.cos(2.70 * y + 0.6)
    return np.maximum(h, 0.0) + 0.15


def save_terrain_png(path):
    n = N_GRID
    xs = np.linspace(-10, 10, n)
    ys = np.linspace(-10, 10, n)
    xx, yy = np.meshgrid(xs, ys)
    h = terrain_height(xx, yy)
    gray = np.clip(h / H_MAX * 255.0, 0, 255).astype(np.uint8)
    gray = gray[::-1, :]

    raw = b"".join(b"\x00" + gray[r].tobytes() for r in range(gray.shape[0]))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    w, h_px = gray.shape[1], gray.shape[0]
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h_px, 8, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def load_hfield_data():
    probe = f"""
<mujoco>
  <asset>
    <hfield name="h" file="{TERRAIN_PNG}" size="20 20 {H_MAX} 0.1"/>
  </asset>
  <worldbody>
    <geom type="hfield" hfield="h"/>
  </worldbody>
</mujoco>
"""
    m = mujoco.MjModel.from_xml_string(probe)
    return np.asarray(m.hfield_data).reshape(N_GRID, N_GRID)


def build_xml(seed=0, hdata=None):
    rng = np.random.default_rng(seed)
    nrow, ncol = hdata.shape

    def surface(x, y):
        fx = (x + 10.0) / 20.0 * (ncol - 1)
        fy = (y + 10.0) / 20.0 * (nrow - 1)
        x0 = int(np.floor(fx))
        y0 = int(np.floor(fy))
        x1 = min(x0 + 1, ncol - 1)
        y1 = min(y0 + 1, nrow - 1)
        dx = fx - x0
        dy = fy - y0
        d = (
            hdata[y0, x0] * (1 - dx) * (1 - dy)
            + hdata[y0, x1] * dx * (1 - dy)
            + hdata[y1, x0] * (1 - dx) * dy
            + hdata[y1, x1] * dx * dy
        )
        return 0.1 + d * H_MAX

    tree_xy = [
        (-7, -5), (-5, 2), (-3, -4), (-1, 5), (1, -5),
        (3, 1), (5, -3), (6, 4), (-6, 6), (-8, 0), (4, 6), (7, -1),
    ]
    trees = []
    for i, (tx, ty) in enumerate(tree_xy):
        base = surface(tx, ty)
        th = 1.5 + rng.uniform(0.0, 0.6)
        cr = 0.75 + rng.uniform(0.0, 0.35)
        trees.append(
            f'<body name="tree{i}" pos="{tx:.2f} {ty:.2f} {base:.3f}">'
            f'<geom type="cylinder" size="0.09 {th / 2:.3f}" pos="0 0 {th / 2:.3f}" rgba="0.42 0.26 0.12 1"/>'
            f'<geom type="sphere" size="{cr:.3f}" pos="0 0 {th:.3f}" rgba="0.12 0.5 0.16 1"/>'
            f'</body>'
        )

    rock_xy = [
        (-6, -1), (-2, 2.5), (0.5, -2), (4, 3), (-4, 4.5),
        (2, 5), (-5, -6), (6, -4), (-8, 2), (8, 1),
    ]
    rocks = []
    for i, (rx, ry) in enumerate(rock_xy):
        base = surface(rx, ry)
        sa = rng.uniform(0.3, 0.55)
        sb = rng.uniform(0.22, 0.42)
        sc = rng.uniform(0.16, 0.32)
        rz = base + sc * 0.7
        rocks.append(
            f'<body name="rock{i}" pos="{rx:.2f} {ry:.2f} {rz:.3f}">'
            f'<geom type="ellipsoid" size="{sa:.3f} {sb:.3f} {sc:.3f}" rgba="0.55 0.55 0.58 1"/>'
            f'</body>'
        )

    bush_xy = [
        (bx, by) for bx in np.linspace(-8, 8, 11) for by in np.linspace(-8, 8, 11)
    ]
    bushes = []
    bi = 0
    for bx, by in bush_xy:
        if any((bx - tx) ** 2 + (by - ty) ** 2 < 1.2 for tx, ty in tree_xy):
            continue
        if any((bx - rx) ** 2 + (by - ry) ** 2 < 0.9 for rx, ry in rock_xy):
            continue
        base = surface(bx, by)
        br = rng.uniform(0.16, 0.32)
        bushes.append(
            f'<body name="bush{bi}" pos="{bx:.2f} {by:.2f} {base + br * 0.4:.3f}">'
            f'<geom type="sphere" size="{br:.3f}" rgba="0.15 0.58 0.2 1"/>'
            f'</body>'
        )
        bi += 1

    xml = f"""
<mujoco model="outdoor_scene">
  <compiler angle="degree"/>
  <statistic center="0 0 0.8" extent="15"/>
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <asset>
    <hfield name="terrain" file="{TERRAIN_PNG}" size="20 20 {H_MAX} 0.1"/>
  </asset>
  <worldbody>
    <geom name="ground" type="hfield" hfield="terrain" rgba="0.22 0.48 0.18 1"/>
    <light name="sun" pos="5 5 25" dir="-0.2 -0.2 -1" diffuse="0.85 0.85 0.8" specular="0.2 0.2 0.2"/>
    {''.join(trees)}
    {''.join(rocks)}
    {''.join(bushes)}
  </worldbody>
</mujoco>
"""
    return xml


def run(headless=False):
    if os.path.exists(SCENE_XML):
        model = mujoco.MjModel.from_xml_path(SCENE_XML)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        # 先让废墟、楼板落定，避免打开窗口时看到悬空物体
        for _ in range(2500):
            mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        lookat = [0.0, 0.0, 33.2]
        distance = 110.0
    else:
        save_terrain_png(TERRAIN_PNG)
        hdata = load_hfield_data()
        xml = build_xml(hdata=hdata)
        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        lookat = [0.0, 0.0, 0.8]
        distance = 18.0

    if headless:
        print("nbody =", model.nbody, "ngeom =", model.ngeom, "ncam =", model.ncam)
        return

    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        viewer.cam.lookat[:] = lookat
        viewer.cam.distance = distance
        viewer.cam.azimuth = 45
        viewer.cam.elevation = 25
        while viewer.is_running():
            mujoco.mj_step(model, data)
            viewer.sync()


if __name__ == "__main__":
    run(headless="--headless" in sys.argv)
