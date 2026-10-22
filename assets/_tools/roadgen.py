r"""把折线地形路生成贴合地面的 ribbon 网格（OBJ + UV），给 MuJoCo 当 mesh 用。

v2 相比 v1：
- 横截面 3 个顶点（左/中/右），中间压 4 cm 形成车辙凹陷
- 宽度沿路缓慢起伏（±18%），不再是一条等宽带子
- UV 按真实米数铺（3 m 一个贴图循环），不再拉伸
- 采样步长 0.6 m、抬升 0.06 m，减少和地形的 z-fighting / 阴影自遮挡
- `write_roads_obj` 支持一次写多条（主路 + 各户门前的支路）

    from roadgen import write_roads_obj
    write_roads_obj([main_pts, spur_pts], widths=[3.6, 2.4], z_of=t.height,
                    out="generated/road.obj")
"""
import math
import os

import numpy as np


def _resample(points, step=0.6):
    out = [points[0]]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-9:
            continue
        n = max(1, int(L / step))
        for i in range(1, n + 1):
            t = i / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def _ribbon(points, width, z_of, lift, tile_m, rut, phase=0.0):
    pts = np.array(_resample(points, 0.6), dtype=float)
    n = len(pts)
    if n < 2:
        return [], [], []
    tang = np.zeros_like(pts)
    tang[1:-1] = pts[2:] - pts[:-2]
    tang[0] = pts[1] - pts[0]
    tang[-1] = pts[-1] - pts[-2]
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
    normal = np.column_stack([-tang[:, 1], tang[:, 0]])

    s = np.linspace(0, 1, n)
    widths = width * (1.0 + 0.18 * np.sin(s * 9.0 + phase) * np.cos(s * 3.7))

    verts, uvs = [], []
    v_acc = 0.0
    for i, (p, nvec) in enumerate(zip(pts, normal)):
        if i > 0:
            v_acc += float(np.linalg.norm(pts[i] - pts[i - 1]))
        hw = widths[i] / 2
        for side, dup in ((-1.0, 0.0), (0.0, rut), (1.0, 0.0)):
            q = p + nvec * hw * side
            verts.append((q[0], q[1], z_of(q[0], q[1]) + lift - dup))
            uvs.append(((0.0 if side < 0 else (1.0 if side > 0 else 0.5)) * (widths[i] / tile_m),
                        v_acc / tile_m))

    faces = []
    for i in range(n - 1):
        a, b, c = 3 * i, 3 * i + 1, 3 * i + 2
        d, e, f = 3 * i + 3, 3 * i + 4, 3 * i + 5
        faces += [(a, b, d), (b, e, d), (b, c, e), (c, f, e)]
    return verts, uvs, faces


def write_roads_obj(polylines, widths, z_of, out_rel, lift=0.06, tile_m=3.0, rut=0.04):
    """多条折线合并成一个 OBJ。widths 可以是单个数字或每条一个。"""
    if not isinstance(widths, (list, tuple)):
        widths = [widths] * len(polylines)

    all_v, all_uv, all_f = [], [], []
    off = 0
    for k, (pl, w) in enumerate(zip(polylines, widths)):
        v, uv, f = _ribbon(pl, w, z_of, lift, tile_m, rut, phase=k * 1.7)
        if not v:
            continue
        all_v += v
        all_uv += uv
        all_f += [(a + off, b + off, c + off) for a, b, c in f]
        off += len(v)

    os.makedirs(os.path.dirname(out_rel) or ".", exist_ok=True)
    with open(out_rel, "w", encoding="utf-8") as fh:
        fh.write("# dirt road ribbon v2 (multi-path, ruts, metric UV)\n")
        np.savetxt(fh, np.array(all_v), fmt="v %.3f %.3f %.3f")
        np.savetxt(fh, np.array(all_uv), fmt="vt %.4f %.4f")
        for a, b, c in all_f:
            fh.write(f"f {a + 1}/{a + 1} {b + 1}/{b + 1} {c + 1}/{c + 1}\n")
    return out_rel, len(all_v), len(all_f)


def write_road_obj(points, width, z_of, out_rel, lift=0.06, tile_m=3.0, rut=0.04):
    """单条道路（向后兼容）。"""
    return write_roads_obj([points], [width], z_of, out_rel, lift=lift, tile_m=tile_m, rut=rut)
