"""验证导入的 Go2：加载、按 home 姿态静置 2 秒、渲染预览。"""
import os
import sys

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
    with open(path, "wb") as f:
        f.write(blob)


HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
ROOT = os.path.join(ASSETS, "props", "robots", "go2_urdf")
os.chdir(ROOT)

m = mujoco.MjModel.from_xml_path("go2_scene.xml")
d = mujoco.MjData(m)
mujoco.mj_resetDataKeyframe(m, d, 0)
print(f"nq={m.nq} nv={m.nv} nu={m.nu} bodies={m.nbody} geoms={m.ngeom} "
      f"mass={m.body_mass.sum():.2f} kg")
tris = 0
for g in range(m.ngeom):
    if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH and m.geom_dataid[g] >= 0:
        tris += int(np.asarray(m.mesh_facenum).ravel()[m.geom_dataid[g]])
print(f"网格三角面 {tris}")

bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
for _ in range(1000):                      # 2 s @ 2 ms
    mujoco.mj_step(m, d)
low = float((d.geom_xpos[:, 2] - np.asarray(m.geom_rbound)).min())
print(f"2 秒后 base z = {d.xpos[bid][2]:.3f} m，最低 geom 底 = {low:.3f} m")

r = mujoco.Renderer(m, 620, 820)
cam = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, "track")
r.update_scene(d, camera=cam)
img = r.render()
r.close()
out = os.path.join(ASSETS, "_go2_urdf.png")
save_png(img, out)
print(f"rendered -> {os.path.relpath(out, ASSETS)}")
