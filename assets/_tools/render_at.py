r"""用自由相机在指定位置取景出图。

    python render_at.py --xml ../demo_v29.xml --lookat -2 -46 2.2 --dist 12 --out ../_shot.png
"""
import argparse
import os
import sys

import mujoco
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "train"))
import terrain_road


def save_png(arr, path):
    import struct
    import zlib
    h, w = arr.shape[:2]
    raw = b"".join(b"\x00" + arr[y, :, :3].astype(np.uint8).tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    blob = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    blob += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    open(path, "wb").write(blob)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True)
    ap.add_argument("--lookat", nargs=3, type=float, default=[0, 0, 1])
    ap.add_argument("--dist", type=float, default=12)
    ap.add_argument("--az", type=float, default=135)
    ap.add_argument("--el", type=float, default=-20)
    ap.add_argument("--steps", type=int, default=600)
    ap.add_argument("--out", required=True)
    ap.add_argument("--w", type=int, default=1000)
    ap.add_argument("--h", type=int, default=700)
    a = ap.parse_args()

    m = terrain_road.load_model(a.xml)
    d = mujoco.MjData(m)
    if m.nkey > 0:
        mujoco.mj_resetDataKeyframe(m, d, 0)
    for _ in range(a.steps):
        mujoco.mj_step(m, d)
    mujoco.mj_forward(m, d)

    r = mujoco.Renderer(m, a.h, a.w)
    cam = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(m, cam)
    cam.lookat[:] = a.lookat
    cam.distance = a.dist
    cam.azimuth = a.az
    cam.elevation = a.el
    r.update_scene(d, camera=cam)
    img = r.render()
    r.close()
    save_png(img, a.out)
    print("saved", a.out)


if __name__ == "__main__":
    main()
