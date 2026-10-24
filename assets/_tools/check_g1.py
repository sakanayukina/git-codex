"""验证 G1：固定基座版加载 + 渲染一张预览图。"""
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


HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
os.chdir(os.path.join(ASSETS, "props", "robots", "g1"))

m = mujoco.MjModel.from_xml_path("g1_scene.xml")
d = mujoco.MjData(m)
mujoco.mj_forward(m, d)
for _ in range(500):
    mujoco.mj_step(m, d)

tris = 0
for g in range(m.ngeom):
    if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH and m.geom_dataid[g] >= 0:
        tris += int(np.asarray(m.mesh_facenum).ravel()[m.geom_dataid[g]])
low = float((d.geom_xpos[:, 2] - np.asarray(m.geom_rbound)).min())
print(f"nq={m.nq} nu={m.nu} bodies={m.nbody} geoms={m.ngeom} tris={tris} "
      f"mass={m.body_mass.sum():.1f} kg")
print(f"骨盆 z={d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'pelvis')][2]:.3f} m")

r = mujoco.Renderer(m, 700, 520)
cam = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, "track")
r.update_scene(d, camera=cam)
img = r.render()
r.close()
out = os.path.join(ASSETS, "_g1_scene.png")
save_png(img, out)
print("rendered ->", os.path.relpath(out, ASSETS))
