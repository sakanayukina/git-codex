"""预览：把 maple 的树皮+树叶两个 mesh 放进一个临时 MJCF 里渲染。"""
import os
import struct
import zlib

import mujoco
import numpy as np

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
D = "props/imported/maple"
parts = sorted(f for f in os.listdir(D) if f.endswith(".obj"))

assets, geoms = [], []
for i, obj in enumerate(parts):
    stem = obj[:-4]
    png = f"{stem}_diffuse.png"
    assets.append(f'<mesh name="m{i}" file="{D}/{obj}" inertia="shell"/>')
    if os.path.exists(os.path.join(D, png)):
        assets.append(f'<texture name="t{i}" type="2d" file="{D}/{png}"/>')
        assets.append(f'<material name="mat{i}" texture="t{i}"/>')
        geoms.append(f'<geom type="mesh" mesh="m{i}" material="mat{i}" contype="0" conaffinity="0"/>')
    else:
        geoms.append(f'<geom type="mesh" mesh="m{i}" rgba="0.4 0.5 0.3 1" contype="0" conaffinity="0"/>')

xml = f"""<mujoco>
  <visual><global offwidth="900" offheight="800"/>
    <headlight ambient="0.55 0.55 0.55" diffuse="0.7 0.7 0.7" specular="0.08 0.08 0.08"/></visual>
  <asset>{''.join(assets)}</asset>
  <worldbody>
    <light pos="8 -8 14" dir="-0.4 0.4 -1" diffuse="0.7 0.7 0.65" castshadow="true"/>
    {''.join(geoms)}
  </worldbody>
</mujoco>"""

m = mujoco.MjModel.from_xml_string(xml)
d = mujoco.MjData(m)
mujoco.mj_forward(m, d)
print("nmesh", m.nmesh, "ntex", m.ntex)

cam = mujoco.MjvCamera()
mujoco.mjv_defaultCamera(cam)
cam.lookat[:] = [0, 0, float(m.stat.center[2])]
cam.distance = float(m.stat.extent) * 2.0
cam.azimuth = 40
cam.elevation = 12
r = mujoco.Renderer(m, 640, 720)
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


save_png(img, "_maple_preview.png")
print("saved _maple_preview.png", img.shape, "mean", round(float(img.mean()), 1))
