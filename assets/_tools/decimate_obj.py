r"""把单个 OBJ 减面到指定面数（顶点聚类，保留 UV/法线）。适合石头、墙这类实心件。

    python decimate_obj.py --in ..\\props\\rocks\\rock_07\\rock_07_1k.obj --out ..\\props\\rocks\\rock_07\\rock_07_low.obj --max-tris 1200
"""
import argparse
import os

import numpy as np

import fetch_ph_model as fpm


def parse(path):
    v, uv, nrm, faces = [], [], [], []
    for ln in open(path, encoding="utf-8", errors="ignore"):
        if ln.startswith("v "):
            v.append([float(x) for x in ln.split()[1:4]])
        elif ln.startswith("vt "):
            uv.append([float(x) for x in ln.split()[1:3]])
        elif ln.startswith("vn "):
            nrm.append([float(x) for x in ln.split()[1:4]])
        elif ln.startswith("f "):
            idx = []
            for tok in ln.split()[1:]:
                idx.append(int(tok.split("/")[0]) - 1)      # 只用位置索引
            if len(idx) == 3:
                faces.append(idx)
            elif len(idx) > 3:                              # 三角化扇形
                for k in range(1, len(idx) - 1):
                    faces.append([idx[0], idx[k], idx[k + 1]])
    return v, uv, nrm, faces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    ap.add_argument("--max-tris", type=int, default=1200)
    args = ap.parse_args()

    v, uv, nrm, faces = parse(args.src)
    v = np.array(v, dtype="f8")
    faces = np.array(faces, dtype="i8")
    print(f"{os.path.basename(args.src)}: {len(faces)} tris, {len(v)} verts")
    # 没有 UV 时补零，decimate 需要三者同长
    if len(uv) != len(v):
        uv = [0.5, 0.5] * 0 + [[0.5, 0.5]] * len(v)
    if len(nrm) != len(v):
        nrm = [[0.0, 0.0, 1.0]] * len(v)
    v2, uv2, n2, f2 = fpm.decimate(v, np.array(uv, dtype="f8"), np.array(nrm, dtype="f8"),
                                   faces, args.max_tris)
    with open(args.dst, "w", encoding="utf-8") as fh:
        fh.write(f"# decimated from {os.path.basename(args.src)} -> {len(f2)} tris\n")
        np.savetxt(fh, v2, fmt="v %.4f %.4f %.4f")
        np.savetxt(fh, uv2, fmt="vt %.5f %.5f")
        np.savetxt(fh, n2, fmt="vn %.4f %.4f %.4f")
        ff = f2 + 1
        fh.write("".join(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n" for a, b, c in ff.tolist()))
    print(f"-> {os.path.basename(args.dst)}: {len(f2)} tris, {len(v2)} verts")


if __name__ == "__main__":
    main()
