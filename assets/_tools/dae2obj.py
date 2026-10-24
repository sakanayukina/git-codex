r"""把 COLLADA (.dae) 转成 OBJ —— MuJoCo 不认 DAE，URDF 里的 Go2 网格全是 DAE。

    python dae2obj.py --in ..\props\robots\go2_urdf\meshes\foot.dae --out ..\foot.obj

处理要点：
- `<node>` 里的 `<matrix>/<translate>/<rotate>/<scale>` 要累乘（导出器常用 Y-up→Z-up 的旋转）
- `<triangles>` / `<polylist>` / `<tristrips>` 三种面表示都支持
- 只取 POSITION / NORMAL，UV 丢掉（URDF 用 material 颜色，不需要贴图）
"""
import argparse
import os
import xml.etree.ElementTree as ET

import numpy as np

NS = "{http://www.collada.org/2005/11/COLLADASchema}"


def tag(el):
    return el.tag.split("}")[-1]


def floats(text):
    return np.fromstring(text or "", sep=" ")


def unit_matrix():
    return np.eye(4)


def axis_angle(axis, deg):
    ax = np.array(axis, dtype=float)
    n = np.linalg.norm(ax)
    if n < 1e-12:
        return unit_matrix()
    ax /= n
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    x, y, z = ax
    m = np.eye(4)
    m[:3, :3] = np.array([
        [c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
        [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
        [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)],
    ])
    return m


def node_transform(node):
    """COLLADA 的 <matrix> 在文件里按行写，但语义是列主序 → 读成行主序再转置。

    实测 unitree 的 DAE：读成行主序直接用，结果与 menagerie 的 OBJ 一致。
    """
    m = unit_matrix()
    for ch in node:
        t = tag(ch)
        if t == "matrix":
            vals = floats(ch.text)
            if vals.size == 16:
                m = m @ vals.reshape(4, 4)
        elif t == "translate":
            t4 = unit_matrix()
            t4[:3, 3] = floats(ch.text)[:3]
            m = m @ t4
        elif t == "rotate":
            v = floats(ch.text)
            m = m @ axis_angle(v[:3], v[3])
        elif t == "scale":
            s = floats(ch.text)[:3]
            s4 = unit_matrix()
            s4[0, 0], s4[1, 1], s4[2, 2] = s
            m = m @ s4
        elif t in ("node", "instance_geometry"):
            continue
    return m


def read_geometry(geom):
    """返回 (verts Nx3, normals Nx3 或 None, faces Mx3) —— 只处理第一个 mesh。"""
    mesh = geom.find(f"{NS}mesh")
    if mesh is None:
        return None
    # 源：按 id 索引 float_array
    sources = {}
    for src in mesh.findall(f"{NS}source"):
        fa = src.find(f"{NS}float_array")
        acc = src.find(f"{NS}technique_common/{NS}accessor")
        if fa is None or acc is None:
            continue
        stride = int(acc.get("stride", "3"))
        data = floats(fa.text)
        sources[src.get("id")] = data.reshape(-1, stride)
    verts_id = None
    vtx = mesh.find(f"{NS}vertices")
    if vtx is not None:
        for inp in vtx.findall(f"{NS}input"):
            if inp.get("semantic") == "POSITION":
                verts_id = inp.get("source", "").lstrip("#")
    if verts_id is None or verts_id not in sources:
        return None
    verts = sources[verts_id][:, :3]

    prim = None
    for cand in ("triangles", "polylist", "tristrips", "polygons"):
        prim = mesh.find(f"{NS}{cand}")
        if prim is not None:
            break
    if prim is None:
        return None

    inputs = [(i.get("semantic"), int(i.get("offset", "0")), i.get("source", "").lstrip("#"))
              for i in prim.findall(f"{NS}input")]
    stride = max(o for _, o, _ in inputs) + 1
    vtx_off = next((o for s, o, _ in inputs if s == "VERTEX"), 0)
    nrm_off = next((o for s, o, _ in inputs if s == "NORMAL"), None)
    p = floats(prim.find(f"{NS}p").text).astype(int)
    p = p.reshape(-1, stride)

    def tri_indices(idx_rows):
        return [int(r[vtx_off]) for r in idx_rows]

    faces = []
    kind = tag(prim)
    if kind == "triangles":
        for i in range(0, len(p) - 2, 3):
            faces.append(tri_indices(p[i:i + 3]))
    elif kind == "polylist":
        vc = floats(prim.find(f"{NS}vcount").text).astype(int)
        k = 0
        for c in vc:
            rows = p[k:k + c]
            k += c
            for j in range(1, c - 1):          # 扇形三角化
                faces.append(tri_indices(rows[[0, j, j + 1]]))
    elif kind == "tristrips":
        for strip_start in range(0, len(p), 3):
            rows = p[strip_start:strip_start + 3]
            if len(rows) == 3:
                faces.append(tri_indices(rows))
    return verts, (nrm_off, p, inputs), faces


def convert(src, dst):
    tree = ET.parse(src)
    root = tree.getroot()

    # 节点树：geometry id -> 世界变换（累乘）
    transforms = {}

    def walk(node, parent):
        m = parent @ node_transform(node)
        for ch in node:
            if tag(ch) == "instance_geometry":
                gid = ch.get("url", "").lstrip("#")
                transforms.setdefault(gid, []).append(m)
            elif tag(ch) == "node":
                walk(ch, m)

    for vs in root.iter(f"{NS}visual_scene"):
        for node in vs.findall(f"{NS}node"):
            walk(node, unit_matrix())

    all_v, all_f = [], []
    base = 0
    for geom in root.iter(f"{NS}geometry"):
        gid = geom.get("id")
        got = read_geometry(geom)
        if not got:
            continue
        verts, _, faces = got
        for m in transforms.get(gid, [unit_matrix()]):
            v4 = np.hstack([verts, np.ones((len(verts), 1))])
            w = (m @ v4.T).T[:, :3]
            all_v.append(w)
            all_f.append(np.array(faces) + base)
            base += len(w)

    if not all_v:
        raise SystemExit(f"no geometry converted in {src}")
    V = np.vstack(all_v)
    F = np.vstack(all_f)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(f"# converted from {os.path.basename(src)} (COLLADA -> OBJ)\n")
        np.savetxt(fh, V, fmt="v %.5f %.5f %.5f")
        # 法线重算即可：DAE 的法线索引和多边形不一一对应，硬搬容易错位
        f1 = F + 1
        fh.write("".join(f"f {a} {b} {c}\n" for a, b, c in f1.tolist()))
    return V, F


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    args = ap.parse_args()
    V, F = convert(args.src, args.dst)
    lo, hi = V.min(0), V.max(0)
    print(f"{os.path.basename(args.dst):<22} {len(F):7d} tris  "
          f"bbox {hi[0]-lo[0]:.3f} x {hi[1]-lo[1]:.3f} x {hi[2]-lo[2]:.3f} m  "
          f"z {lo[2]:+.3f}..{hi[2]:+.3f}")


if __name__ == "__main__":
    main()
