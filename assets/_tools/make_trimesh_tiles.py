r"""把 trimesh 地形拆成凸 quad，解决 MuJoCo "mesh 碰撞按凸包" 的问题。

    python make_trimesh_tiles.py --half 20 --cell 2      # 20 m 半宽 → 20×20 = 400 块
    python make_trimesh_tiles.py --half 40 --cell 2      # 40 m 半宽 → 40×40 = 1600 块

每块是 4 顶点 2 三角面（各自是凸的），MuJoCo 对单个三角面是精确碰撞。
产物：assets/train/_terrain/tiles_<half>_<cell>.xml
"""
import argparse
import os
import re

import numpy as np

from make_robot_on_trimesh import patch_height

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
ROBOT = os.path.join(ASSETS, "train", "ref", "mjcf", "go2_visual.xml")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", type=float, default=20.0)
    ap.add_argument("--cell", type=float, default=2.0)
    ap.add_argument("--robot", action="store_true", help="同时放上 Go2")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    gx, gy, zi = patch_height(half=a.half, res=a.cell)
    n = len(gx)
    out = a.out or os.path.join(ASSETS, "train", "_terrain",
                                "tiles_%d_%g%s.xml" % (int(a.half), a.cell, "_robot" if a.robot else ""))

    meshes, geoms = [], []
    for j in range(n - 1):
        for i in range(n - 1):
            x0, x1 = gx[i], gx[i + 1]
            y0, y1 = gy[j], gy[j + 1]
            z00, z10 = zi[j, i], zi[j, i + 1]
            z01, z11 = zi[j + 1, i], zi[j + 1, i + 1]
            name = "t_%d_%d" % (j, i)
            meshes.append(
                '<mesh name="%s" vertex="%g %g %g  %g %g %g  %g %g %g  %g %g %g" '
                'face="0 1 2  1 3 2" inertia="shell"/>' % (name, x0, y0, z00, x1, y0, z10,
                                           x0, y1, z01, x1, y1, z11))
            geoms.append('<geom name="g_%s" type="mesh" mesh="%s" '
                         'friction="1.0 0.02 0.001" rgba="0.45 0.5 0.42 1"/>' % (name, name))

    robot = open(ROBOT, encoding="utf-8").read() if a.robot else None
    if a.robot:
        dflt = robot[robot.index("<default>"):robot.rindex("</default>") + len("</default>")]
        rasset = re.search(r"<asset>(.*?)</asset>", robot, re.S).group(1)
        rbody = re.search(r"<worldbody>(.*?)</worldbody>", robot, re.S).group(1)
        ract = re.search(r"<actuator>(.*?)</actuator>", robot, re.S).group(1)
        ci = n // 2
        x, y, h = gx[ci], gy[ci], zi[ci, ci]
        rbody = re.sub(r'<body name="base" pos="[^"]*"',
                       '<body name="base" pos="%.3f %.3f %.3f"' % (x, y, h + 0.445), rbody, count=1)
    else:
        dflt, rasset, rbody, ract = "", "", "", ""

    xml = """<mujoco model="tiled terrain %g m">
  <compiler angle="radian"/>
  <option timestep="0.005" integrator="implicitfast" solver="Newton" iterations="100" ls_iterations="50"/>
  <visual><global offwidth="1280" offheight="800"/></visual>
  %s
  <asset>
%s
%s
  </asset>
  <worldbody>
    <light pos="0 0 20" dir="0 0 -1" directional="true"/>
%s
%s
  </worldbody>
  %s
</mujoco>
""" % (a.half, dflt, rasset, "\n".join(meshes), "\n".join(geoms), rbody,
       ("<actuator>%s</actuator>" % ract) if ract else "")
    open(out, "w", encoding="utf-8").write(xml)
    print("tiles %d×%d = %d 块（每块 4 顶点 2 面）" % (n - 1, n - 1, (n - 1) ** 2))
    print("wrote", out)

    import time
    import mujoco
    t = time.time()
    m = mujoco.MjModel.from_xml_path(out)
    print("加载 %.2f s，ngeom=%d nmesh=%d" % (time.time() - t, m.ngeom, m.nmesh))


if __name__ == "__main__":
    main()
