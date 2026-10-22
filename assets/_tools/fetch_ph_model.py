r"""Download a Poly Haven model (glTF) and convert it to MuJoCo-friendly OBJ + PNG.

MuJoCo cannot read glTF, so we flatten the scene graph into a single OBJ (Z-up, metres),
optionally decimating heavy photogrammetry (a fir tree is ~7M triangles / ~400 MB of bin).
Textures are converted to PNG; the source glTF is deleted by default to save disk.

Usage:
    python fetch_ph_model.py --id boulder_01 --res 1k --out ..\props\rocks
    python fetch_ph_model.py --id fir_tree_01 --res 1k --max-tris 40000 --out ..\props\trees
"""
import argparse
import json
import os
import struct
import urllib.request

import numpy as np
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "*/*"}
API = "https://api.polyhaven.com/files/{}"

DTYPE = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16,
         5125: np.uint32, 5126: np.float32}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def http_get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        return r.read()


def download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(http_get(url))
    os.replace(tmp, path)
    return path


def read_accessor(gltf, base, idx):
    """Read an accessor without loading the whole buffer (glTF files can be 400 MB)."""
    acc = gltf["accessors"][idx]
    n = acc["count"]
    ncomp = NCOMP[acc["type"]]
    dt = DTYPE[acc["componentType"]]
    itemsize = np.dtype(dt).itemsize
    if "bufferView" not in acc:
        return np.zeros((n, ncomp), dtype=np.float64)
    bv = gltf["bufferViews"][acc["bufferView"]]
    stride = bv.get("byteStride") or ncomp * itemsize
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    path = os.path.join(base, gltf["buffers"][bv["buffer"]]["uri"])
    with open(path, "rb") as f:
        f.seek(start)
        blob = f.read(stride * (n - 1) + ncomp * itemsize)
    rows = np.frombuffer(blob, dtype=np.uint8)
    view = np.lib.stride_tricks.as_strided(
        rows, shape=(n, ncomp * itemsize), strides=(stride, 1), writeable=False)
    return view.copy().view(dt).reshape(n, ncomp).astype(np.float64)


def node_matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    t = np.array(node.get("translation", [0, 0, 0]), dtype=np.float64)
    r = np.array(node.get("rotation", [0, 0, 0, 1]), dtype=np.float64)
    s = np.array(node.get("scale", [1, 1, 1]), dtype=np.float64)
    x, y, z, w = r
    rot = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    m = np.eye(4)
    m[:3, :3] = rot * s[None, :]
    m[:3, 3] = t
    return m


def walk(gltf, node_idx, parent, out):
    node = gltf["nodes"][node_idx]
    m = parent @ node_matrix(node)
    if "mesh" in node:
        out.append((node["mesh"], m))
    for c in node.get("children", []):
        walk(gltf, c, m, out)


def decimate(v, uv, nrm, faces, max_tris, verbose=True):
    """UV-preserving vertex-clustering decimation (no external mesh libs)."""
    if max_tris <= 0 or len(faces) <= max_tris:
        return v, uv, nrm, faces
    lo, hi = v.min(0), v.max(0)
    ext = np.maximum(hi - lo, 1e-6)
    target_v = max(int(max_tris * 0.62), 64)

    best = None
    prev = None
    for g in (16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024):
        key = np.floor((v - lo) / ext * g).astype(np.int64)
        key = (key[:, 0] * (g + 2) + key[:, 1]) * (g + 2) + key[:, 2]
        uniq, inv = np.unique(key, return_inverse=True)
        cand = (inv, len(uniq), g)
        if best is None or abs(len(uniq) - target_v) < abs(best[1] - target_v):
            best = cand
        if len(uniq) >= target_v:
            break
        prev = cand
    if prev is not None and abs(prev[1] - target_v) < abs(best[1] - target_v):
        best = prev

    inv, nv, g = best
    cnt = np.bincount(inv, minlength=nv).astype(np.float64)[:, None]
    nv_v = np.zeros((nv, 3))
    nv_uv = np.zeros((nv, 2))
    nv_n = np.zeros((nv, 3))
    for i in range(3):
        nv_v[:, i] = np.bincount(inv, weights=v[:, i], minlength=nv)
    for i in range(2):
        nv_uv[:, i] = np.bincount(inv, weights=uv[:, i], minlength=nv)
    for i in range(3):
        nv_n[:, i] = np.bincount(inv, weights=nrm[:, i], minlength=nv)
    nv_v /= cnt
    nv_uv /= cnt
    nv_n /= np.maximum(np.linalg.norm(nv_n, axis=1, keepdims=True), 1e-12)

    f = inv[faces]
    keep = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    f = f[keep]
    if verbose:
        print(f"  decimated {len(faces)} -> {len(f)} tris (grid {g}, {nv} verts)")
    return nv_v, nv_uv, nv_n, f


def convert(model_dir, stem, max_tris=0):
    with open(os.path.join(model_dir, f"{stem}.gltf"), "r", encoding="utf-8") as fh:
        gltf = json.load(fh)
    if any("draco" in str(e).lower() for e in gltf.get("extensionsUsed", [])):
        raise SystemExit("compressed (draco) glTF not supported")

    inst = []
    scene = gltf.get("scenes", [{}])[gltf.get("scene", 0)]
    for n in scene.get("nodes", []):
        walk(gltf, n, np.eye(4), inst)

    verts, uvs, norms, faces = [], [], [], []
    offset = 0
    for mesh_idx, mat in inst:
        for prim in gltf["meshes"][mesh_idx]["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            pos = read_accessor(gltf, model_dir, prim["attributes"]["POSITION"])
            pos = (mat[:3, :3] @ pos.T).T + mat[:3, 3]
            base = offset
            offset += len(pos)
            verts.append(pos)
            if "TEXCOORD_0" in prim["attributes"]:
                uv = read_accessor(gltf, model_dir, prim["attributes"]["TEXCOORD_0"])
                uvs.append(np.column_stack([uv[:, 0], 1.0 - uv[:, 1]]))
            else:
                uvs.append(np.zeros((len(pos), 2)))
            if "NORMAL" in prim["attributes"]:
                nr = read_accessor(gltf, model_dir, prim["attributes"]["NORMAL"])
                nr = (mat[:3, :3] @ nr.T).T
                nr /= np.maximum(np.linalg.norm(nr, axis=1, keepdims=True), 1e-12)
                norms.append(nr)
            else:
                norms.append(np.tile([0.0, 0.0, 1.0], (len(pos), 1)))
            if "indices" in prim:
                idx = read_accessor(gltf, model_dir, prim["indices"]).astype(np.int64).ravel()
            else:
                idx = np.arange(len(pos), dtype=np.int64)
            ntri = len(idx) // 3
            faces.append(idx[:ntri * 3].reshape(-1, 3) + base)

    v = np.vstack(verts)
    uv = np.vstack(uvs)
    nrm = np.vstack(norms)
    f = np.vstack(faces)

    v, uv, nrm, f = decimate(v, uv, nrm, f, max_tris)

    tex_png = None
    for root, _dirs, files in os.walk(model_dir):
        for name in sorted(files):
            low = name.lower()
            if ("diff" in low or "albedo" in low or "basecolor" in low) and low.endswith((".jpg", ".jpeg", ".png")):
                tex_png = os.path.join(model_dir, f"{stem}_diffuse.png")
                Image.open(os.path.join(root, name)).convert("RGB").save(tex_png)
                break
        if tex_png:
            break

    # glTF: Y-up right-handed, metres.  MJCF: Z-up.  (x, y, z)_mj = (x, -z, y)_gltf
    vmj = np.column_stack([v[:, 0], -v[:, 2], v[:, 1]])

    obj_path = os.path.join(model_dir, f"{stem}.obj")
    with open(obj_path, "w", encoding="utf-8") as fh:
        fh.write(f"# Poly Haven {stem} -> MuJoCo (Z-up, metres)\n")
        fh.write(f"mtllib {stem}.mtl\n")
        np.savetxt(fh, vmj, fmt="v %.6f %.6f %.6f")
        np.savetxt(fh, uv, fmt="vt %.6f %.6f")
        np.savetxt(fh, nrm, fmt="vn %.6f %.6f %.6f")
        fh.write(f"usemtl {stem}\n")
        np.savetxt(fh, f + 1, fmt="f %d/%d/%d")

    with open(os.path.join(model_dir, f"{stem}.mtl"), "w", encoding="utf-8") as fh:
        fh.write(f"newmtl {stem}\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nd 1\nillum 1\n")
        if tex_png:
            fh.write(f"map_Kd {os.path.basename(tex_png)}\n")

    size = vmj.max(0) - vmj.min(0)
    print(f"  {stem}: {len(f)} tris, size {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} m")
    return obj_path, tex_png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--res", default="1k")
    ap.add_argument("--out", default=".")
    ap.add_argument("--max-tris", type=int, default=0, help="0 = keep full resolution")
    ap.add_argument("--keep-source", action="store_true")
    args = ap.parse_args()

    meta = json.loads(http_get(API.format(args.id)))
    if "gltf" not in meta:
        raise SystemExit(f"{args.id}: no glTF format, has {list(meta)}")
    entry = meta["gltf"][args.res]["gltf"]
    model_dir = os.path.join(args.out, args.id)
    os.makedirs(model_dir, exist_ok=True)

    stem = entry["url"].split("/")[-1].replace(".gltf", "")
    src_gltf = download(entry["url"], os.path.join(model_dir, f"{stem}.gltf"))
    for rel, info in entry["include"].items():
        download(info["url"], os.path.join(model_dir, rel.replace("/", os.sep)))
    convert(model_dir, stem, args.max_tris)

    if not args.keep_source:
        for root, _dirs, files in os.walk(model_dir):
            for name in files:
                if name.endswith((".gltf", ".bin", ".glb", ".jpg", ".jpeg")):
                    os.remove(os.path.join(root, name))
        for root, dirs, _files in os.walk(model_dir, topdown=False):
            if root != model_dir and not os.listdir(root):
                os.rmdir(root)


if __name__ == "__main__":
    main()
