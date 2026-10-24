"""用自由相机渲染院子（XML 里的相机对 30 m 场景不好取景）。"""
import os

import mujoco
import numpy as np


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


ASSETS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
m = mujoco.MjModel.from_xml_path(os.path.join(ASSETS, "yard_full.xml"))
d = mujoco.MjData(m)
if m.nkey > 0:
    mujoco.mj_resetDataKeyframe(m, d, 0)
for _ in range(400):                 # 0.8 s
    mujoco.mj_step(m, d)
mujoco.mj_forward(m, d)

b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
print(f"Go2 base z after 0.8 s: {d.xpos[b][2]:.3f} m")

r = mujoco.Renderer(m, 700, 1000)
cam = mujoco.MjvCamera()
mujoco.mjv_defaultFreeCamera(m, cam)
cam.lookat[:] = [0.0, 2.0, 0.4]
cam.distance = 22.0
cam.azimuth = 140.0
cam.elevation = -32.0
r.update_scene(d, camera=cam)
img = r.render()
r.close()
out = os.path.join(ASSETS, "_yard.png")
save_png(img, out)
print("rendered ->", os.path.relpath(out, ASSETS))
