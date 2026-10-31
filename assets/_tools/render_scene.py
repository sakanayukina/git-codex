"""Render an MJCF scene to PNG (for eyeballing the assembled rescue scene)."""
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
    with open(path, "wb") as f:
        f.write(blob)


xml_path, out = sys.argv[1], sys.argv[2]
w, h = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (1100, 620)
steps = int(sys.argv[5]) if len(sys.argv) > 5 else 0
cam_idx = int(sys.argv[6]) if len(sys.argv) > 6 else 0

model = terrain_road.load_model(xml_path)
data = mujoco.MjData(model)
print(f"nbody={model.nbody} ngeom={model.ngeom} nmesh={model.nmesh} ntex={model.ntex}")
# 有 keyframe 就先按它摆好姿态（否则机器人从零位起步会瘫成一坨）
if model.nkey > 0:
    mujoco.mj_resetDataKeyframe(model, data, 0)
    print(f"reset to keyframe[0] = {model.key(0).name or '(unnamed)'}")
for _ in range(steps):
    mujoco.mj_step(model, data)
mujoco.mj_forward(model, data)

cam = mujoco.MjvCamera()
mujoco.mjv_defaultCamera(cam)
if model.ncam:
    cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
    cam.fixedcamid = min(cam_idx, model.ncam - 1)
else:
    cam.lookat[:] = [0, 0, float(model.stat.center[2])]
    cam.distance = float(model.stat.extent) * 2.2
    cam.azimuth = 120
    cam.elevation = 25

r = mujoco.Renderer(model, h, w)
r.update_scene(data, camera=cam)
img = r.render()
save_png(img, out)
print("saved", out, img.shape, "mean", round(float(img.mean()), 1))
