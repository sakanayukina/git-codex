r"""把可走 Go2 放到 trimesh 地形补丁上（训练分支，只用于实验）。

    python make_robot_on_trimesh.py                 # 自动选最平的一块放机器人
    python make_robot_on_trimesh.py --at 0 -10

产物：assets/train/_terrain/robot_on_patch.xml
"""
import argparse
import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
PATCH = os.path.join(ASSETS, "train", "_terrain", "dem_patch.xml")
ROBOT = os.path.join(ASSETS, "train", "ref", "mjcf", "go2_visual.xml")
OUT = os.path.join(ASSETS, "train", "_terrain", "robot_on_patch.xml")
NPZ = os.path.join(ASSETS, "terrain", "dem_float.npz")


def patch_height(half=40.0, res=2.0):
    """重建补丁高度场（与 make_terrain_trimesh.py 同一算法），用于选点和贴地。"""
    d = np.load(NPZ)
    z = d["z"].astype(np.float64)
    extent = float(d["extent"])
    H, W = z.shape
    cell = extent / W
    xs = (np.arange(W) + 0.5) * cell - extent / 2
    ys = extent / 2 - (np.arange(H) + 0.5) * cell
    n = int(2 * half / res) + 1
    gx = np.linspace(-half, half, n)
    gy = np.linspace(half, -half, n)
    GX, GY = np.meshgrid(gx, gy)
    ix = np.interp(GX.ravel(), xs, np.arange(W))
    iy = np.interp(GY.ravel(), ys[::-1], np.arange(H))
    zi = z[np.clip(iy.round().astype(int), 0, H - 1),
           np.clip(ix.round().astype(int), 0, W - 1)].reshape(n, n)
    return gx, gy, zi - zi.mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", nargs=2, type=float, default=None)
    a = ap.parse_args()

    gx, gy, zi = patch_height()
    ddx, ddy = np.gradient(zi, gx[1] - gx[0], gy[1] - gy[0])
    slope = np.degrees(np.arctan(np.hypot(ddx, ddy)))

    if a.at:
        x, y = a.at
        i = int(np.argmin(np.abs(gx - x)))
        j = int(np.argmin(np.abs(gy - y)))
    else:
        # 选一条最平的地带（避开中心最陡区）
        m = np.abs(gx) < 25
        n = np.abs(gy) < 25
        sub = np.where(m[:, None] & n[None, :], slope, 99.0)
        j, i = np.unravel_index(np.argmin(sub), sub.shape)
        x, y = gx[i], gy[j]
    h = float(zi[j, i])

    robot = open(ROBOT, encoding="utf-8").read()
    dflt = robot[robot.index("<default>"):robot.rindex("</default>") + len("</default>")]
    rasset = re.search(r"<asset>(.*?)</asset>", robot, re.S).group(1)
    rbody = re.search(r"<worldbody>(.*?)</worldbody>", robot, re.S).group(1)
    ract = re.search(r"<actuator>(.*?)</actuator>", robot, re.S).group(1)
    mesh = re.search(r'<mesh name="dem_patch" file="([^"]+)"', open(PATCH, encoding="utf-8").read()).group(1)

    rbody = re.sub(r'<body name="base" pos="[^"]*"',
                   '<body name="base" pos="%.3f %.3f %.3f"' % (x, y, h + 0.445), rbody, count=1)
    xml = """<mujoco model="go2 on trimesh">
  <compiler angle="radian"/>
  <option timestep="0.005" integrator="implicitfast" solver="Newton" iterations="100" ls_iterations="50"/>
  <visual>
    <global offwidth="1280" offheight="800"/>
    <headlight diffuse="0.7 0.7 0.7" ambient="0.35 0.35 0.35"/>
  </visual>
  %s
  <asset>
    <mesh name="dem_patch" file="%s" inertia="shell"/>
%s
  </asset>
  <worldbody>
    <light pos="0 0 20" dir="0 0 -1" directional="true"/>
    <geom name="ground" type="mesh" mesh="dem_patch" friction="1.0 0.02 0.001"/>
%s
  </worldbody>
  <actuator>%s</actuator>
</mujoco>
""" % (dflt, mesh, rasset, rbody, ract)
    open(OUT, "w", encoding="utf-8").write(xml)

    import mujoco
    m = mujoco.MjModel.from_xml_path(OUT)
    print("站位 (%.1f, %.1f) 地形高 %.2f m，坡度 %.1f°" % (x, y, h, slope[j, i]))
    print("scene: nq=%d nu=%d ngeom=%d" % (m.nq, m.nu, m.ngeom))


if __name__ == "__main__":
    main()
