r"""预览 props/imported/<name>/ 下的所有 obj（每个 obj 一个 geom + 自己的贴图）。

    python preview_parts.py ruin_uk
"""
import os
import struct
import sys
import zlib

import mujoco
import numpy as np

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
name = sys.argv[1] if len(sys.argv) > 1 else "maple"
D = f"props/imported/{name}"
parts = sorted(f for f in os.listdir(D) if f.endswith(".obj"))

assets, geoms = [], []
for i, obj in enumerate(parts):
    stem = obj[:-4]
    png = f"{stem}_diffuse.png"
    assets.append(f'<mesh name="m{i}" file="{D}/{obj}" inertia="shell"/>')
    if os.path.exists(os.path.join(D, png)):
        assets.append(f'<texture name="t{i}" type="2d" file="{D}/{png}"/>')
        assets.append(f'<material name="mat{i}" texture="t{i}" specular="0.05" shininess="0.1"/>')
        geoms.append(f'<geom type="mesh" mesh="m{i}" material="mat{i}" contype="0" conaffinity="0"/>')
    else:
        geoms.append(f'<geom type="mesh" mesh="m{i}" rgba="0.6 0.58 0.55 1"/>')

xml = f"""<mujoco>
  <visual><global offwidth="900" offheight="800"/>
    <headlight ambient="0.55 0.55 0.55" diffuse="0.7 0.7 0.7" specular="0.05 0.05 0.05"/></visual>
  <asset>{''.join(assets)}</asset>
  <worldbody>
    <light pos="10 -10 18" dir="-0.45 0.45 -1" diffuse="0.7 0.7 0.65" castshadow="true"/>
    {''.join(geoms)}
  </worldbody>
</mujoco>"""

m = mujoco.MjModel.from_xml_string(xml)
d = mujoco.MjData(m)
mujoco.mj_forward(m, d)

cam = mujoco.MjvCamera()
mujoco.mjv_defaultCamera(cam)
cam.lookat[:] = [0, 0, float(m.stat.center[2])]
cam.distance = float(m.stat.extent) * 1.9
cam.azimuth = 35
cam.elevation = 12
r = mujoco.Renderer(m, 640, 760)
r.update_scene(d, camera=cam)
img = r.render()
r.close()


def save_png(a, path):
    h, w = a.shape[:2]
    raw = b"".join(b"\x00" + a[y, :, :3].astype(np.uint8).tobytes() for y in range(h))

    def chunk(t, dd):
        return struct.pack(">I", len(dd)) + t + dd + struct.pack(">I", zlib.crc32(t + dd) & 0xFFFFFFFF)

    blob = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    blob += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    open(path, "wb").write(blob)


out = f"_{name}_preview.png"
save_png(img, out)
print("saved", out, "parts", len(parts), "mean", round(float(img.mean()), 1))
