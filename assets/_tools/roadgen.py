r"""把折线地形路生成一条贴合地面的 ribbon 网格（OBJ + UV），给 MuJoCo 当 mesh 用。

    from roadgen import write_road_obj
    rel = write_road_obj(points, width=3.6, z_of=t.height, out="generated/road.obj")
"""
import math
import os

import numpy as np


def _resample(points, step=1.0):
    """把折线重采样成等间距点。"""
    out = [points[0]]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L / step))
        for i in range(1, n + 1):
            t = i / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def write_road_obj(points, width, z_of, out_rel, lift=0.05, v_repeat=1.6):
    """返回 (相对路径, 顶点数, 三角面数)。"""
    pts = np.array(_resample(points, 1.0), dtype=float)
    # 每点处的切向与法向
    tang = np.zeros_like(pts)
    tang[1:-1] = pts[2:] - pts[:-2]
    tang[0] = pts[1] - pts[0]
    tang[-1] = pts[-1] - pts[-2]
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
    normal = np.column_stack([-tang[:, 1], tang[:, 0]])

    half = width / 2
    verts, uvs = [], []
    v_acc = 0.0
    for i, (p, n) in enumerate(zip(pts, normal)):
        if i > 0:
            v_acc += float(np.linalg.norm(pts[i] - pts[i - 1]))
        for side in (-1, 1):
            q = p + n * half * side
            verts.append((q[0], q[1], z_of(q[0], q[1]) + lift))
            uvs.append((0.0 if side < 0 else 1.0, v_acc / v_repeat))

    faces = []
    for i in range(len(pts) - 1):
        a, b = 2 * i, 2 * i + 1
        c, d = 2 * i + 2, 2 * i + 3
        faces.append((a, b, c))
        faces.append((b, d, c))

    abs_out = out_rel if os.path.isabs(out_rel) else out_rel
    os.makedirs(os.path.dirname(abs_out) or ".", exist_ok=True)
    with open(abs_out, "w", encoding="utf-8") as f:
        f.write("# dirt road ribbon, Z-up, metres, UV along length\n")
        np.savetxt(f, np.array(verts), fmt="v %.3f %.3f %.3f")
        np.savetxt(f, np.array(uvs), fmt="vt %.4f %.4f")
        for a, b, c in faces:
            f.write(f"f {a + 1}/{a + 1} {b + 1}/{b + 1} {c + 1}/{c + 1}\n")
    return out_rel, len(verts), len(faces)
