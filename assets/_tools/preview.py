"""Render a single converted asset to a PNG so we can eyeball it."""
import sys

import mujoco
import numpy as np

obj, png, out = sys.argv[1], sys.argv[2], sys.argv[3]
xml = f"""
<mujoco>
  <visual>
    <global offwidth="800" offheight="800"/>
    <headlight ambient="0.55 0.55 0.55" diffuse="0.7 0.7 0.7" specular="0.1 0.1 0.1"/>
  </visual>
  <asset>
    <mesh name="b" file="{obj}"/>
    <texture name="t" type="2d" file="{png}"/>
    <material name="m" texture="t" specular="0.1" shininess="0.1"/>
  </asset>
  <worldbody>
    <light pos="3 -3 5" dir="-0.4 0.4 -1" diffuse="0.5 0.5 0.5"/>
    <geom type="mesh" mesh="b" material="m"/>
  </worldbody>
</mujoco>
"""
m = mujoco.MjModel.from_xml_string(xml)
d = mujoco.MjData(m)
mujoco.mj_forward(m, d)
verts = np.array([[float(x) for x in ln.split()[1:4]] for ln in open(obj) if ln.startswith("v ")])
lo, hi = verts.min(0), verts.max(0)
center = (lo + hi) / 2
span = float((hi - lo).max())

cam = mujoco.MjvCamera()
mujoco.mjv_defaultCamera(cam)
cam.lookat[:] = center
cam.distance = 2.2 * span
cam.azimuth = 45
cam.elevation = 22

r = mujoco.Renderer(m, 400, 500)
r.update_scene(d, camera=cam)
img = r.render()


def save_png(arr, path):
    """Minimal RGB PNG writer (mujoco env has no PIL)."""
    import struct
    import zlib

    h, w = arr.shape[:2]
    raw = b"".join(b"\x00" + arr[y, :, :3].astype(np.uint8).tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    blob = b"\x89PNG\r\n\x1a\n"
    blob += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    blob += chunk(b"IDAT", zlib.compress(raw, 6))
    blob += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(blob)


save_png(img, out)
print("saved", out, img.shape, "mean", round(float(img.mean()), 1))
