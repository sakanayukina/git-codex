r"""按材质拆分转换 glTF/GLB：每个材质输出一个 OBJ + 一张 PNG。

Sketchfab 的模型常把一棵树拆成上千个小 mesh（bark/leaf/grass 混在一起），
用单一贴图展平会串色，所以按材质分开导出，MJCF 里一个 body 挂多个 geom。

    python convert_multi.py --src ..\incoming\maple\scene.gltf --name maple --skip grass,groundcover
"""
import argparse
import json
import os
import shutil
import sys
from collections import defaultdict

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import fetch_ph_model as fpm  # noqa: E402
import import_gltf as ig  # noqa: E402


def mat_texture(gltf, mat_idx):
    """材质 -> baseColor 图片文件名（相对 model_dir）。"""
    if mat_idx is None:
        return None
    mat = gltf["materials"][mat_idx]
    tex = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture", {}).get("index")
    if tex is None:
        return None
    src = gltf["textures"][tex].get("source")
    if src is None:
        return None
    return gltf["images"][src].get("uri")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--skip", default="", help="要丢弃的材质名，逗号分隔（如 grass,groundcover）")
    ap.add_argument("--scale", type=float, default=1.0, help="导出时统一缩放")
    ap.add_argument("--target-height", type=float, default=0.0, help="按总高度等比缩放（米）")
    ap.add_argument("--max-tex", type=int, default=2048, help="贴图最长边上限")
    args = ap.parse_args()

    src = args.src
    ext = os.path.splitext(src)[1].lower()
    out_dir = os.path.join(ASSETS, "props", "imported", args.name)
    os.makedirs(out_dir, exist_ok=True)
    stem = args.name

    if ext == ".glb":
        ig.unpack_glb(src, out_dir, stem)
    else:
        shutil.copy2(src, os.path.join(out_dir, f"{stem}.gltf"))
        root = os.path.dirname(os.path.abspath(src))
        for cur, _dirs, files in os.walk(root):          # 贴图常在 textures/ 子目录里
            for f in files:
                if f.lower().endswith((".bin", ".png", ".jpg", ".jpeg")):
                    shutil.copy2(os.path.join(cur, f), os.path.join(out_dir, f))

    gltf = json.load(open(os.path.join(out_dir, f"{stem}.gltf"), encoding="utf-8"))
    gltf = ig.materialize(gltf, out_dir, stem)

    skip = {s.strip().lower() for s in args.skip.split(",") if s.strip()}

    # 展平场景图，按材质归组
    inst = []
    for n in gltf["scenes"][gltf.get("scene", 0)]["nodes"]:
        fpm.walk(gltf, n, np.eye(4), inst)

    groups = defaultdict(lambda: {"v": [], "uv": [], "n": [], "f": [], "base": 0, "tex": None})
    for mesh_idx, M in inst:
        for prim in gltf["meshes"][mesh_idx]["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            mi = prim.get("material")
            mname = gltf["materials"][mi]["name"] if mi is not None else "default"
            if any(k in mname.lower() for k in skip):
                continue
            g = groups[mname]
            if g["tex"] is None:
                g["tex"] = mat_texture(gltf, mi)

            pos = fpm.read_accessor(gltf, out_dir, prim["attributes"]["POSITION"])
            pos = (M[:3, :3] @ pos.T).T + M[:3, 3]
            if "TEXCOORD_0" in prim["attributes"]:
                uv = fpm.read_accessor(gltf, out_dir, prim["attributes"]["TEXCOORD_0"])
                uv = np.column_stack([uv[:, 0], 1.0 - uv[:, 1]])
            else:
                uv = np.zeros((len(pos), 2))
            if "NORMAL" in prim["attributes"]:
                nr = fpm.read_accessor(gltf, out_dir, prim["attributes"]["NORMAL"])
                nr = (M[:3, :3] @ nr.T).T
                nr /= np.maximum(np.linalg.norm(nr, axis=1, keepdims=True), 1e-12)
            else:
                nr = np.tile([0.0, 0.0, 1.0], (len(pos), 1))

            base = g["base"]
            g["base"] += len(pos)
            g["v"].append(pos)
            g["uv"].append(uv)
            g["n"].append(nr)
            if "indices" in prim:
                idx = fpm.read_accessor(gltf, out_dir, prim["indices"]).astype(np.int64).ravel()
            else:
                idx = np.arange(len(pos), dtype=np.int64)
            tri = idx[: len(idx) // 3 * 3].reshape(-1, 3) + base
            g["f"].append(tri)

    # 先算合并包围盒（glTF 是 Y-up，所以"高度"看 Y），据此推出目标缩放
    allv = np.vstack([np.vstack(g["v"]) for g in groups.values() if g["v"]])
    model_h = float(allv[:, 1].max() - allv[:, 1].min())
    scale = args.scale
    if args.target_height and model_h > 1e-9:
        scale = args.target_height / model_h
    print(f"原始高度 {model_h:.2f}（glTF Y-up），缩放系数 {scale:.4f}")

    tex_cache = {}
    report = []
    for mname, g in groups.items():
        v = np.vstack(g["v"]) * scale
        uv = np.vstack(g["uv"])
        nrm = np.vstack(g["n"])
        f = np.vstack(g["f"])
        if len(f) == 0:
            continue
        # glTF Y-up -> MJCF Z-up
        vmj = np.column_stack([v[:, 0], -v[:, 2], v[:, 1]])
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in mname)
        obj_name = f"{stem}_{safe}"
        obj_path = os.path.join(out_dir, f"{obj_name}.obj")
        with open(obj_path, "w", encoding="utf-8") as fh:
            fh.write(f"# {mname} of {stem} (Z-up, m)\n")
            np.savetxt(fh, vmj, fmt="v %.4f %.4f %.4f")
            np.savetxt(fh, uv, fmt="vt %.5f %.5f")
            np.savetxt(fh, nrm, fmt="vn %.4f %.4f %.4f")
            f1 = f + 1
            fh.write("".join(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n" for a, b, c in f1.tolist()))

        png_name = None
        if g["tex"]:
            tex_path = os.path.join(out_dir, g["tex"])
            if not os.path.exists(tex_path):
                tex_path = os.path.join(out_dir, os.path.basename(g["tex"]))
            if os.path.exists(tex_path):
                # 同一个图集常被多个材质共用，按源文件去重，否则 15 份 5.8 MB 白烧 90 MB
                key = os.path.basename(tex_path)
                if key not in tex_cache:
                    im = Image.open(tex_path)
                    # 树叶贴图带 alpha：MuJoCo 没有 alpha 裁剪，合成到草绿底
                    if im.mode in ("RGBA", "LA", "PA"):
                        bg = Image.new("RGB", im.size, (74, 102, 52))
                        bg.paste(im, mask=im.split()[-1])
                        im = bg
                    im = im.convert("RGB")
                    if args.max_tex and max(im.size) > args.max_tex:
                        im.thumbnail((args.max_tex, args.max_tex), Image.LANCZOS)
                    name_out = f"{stem}_atlas_{len(tex_cache)}.png"
                    im.save(os.path.join(out_dir, name_out), optimize=True)
                    tex_cache[key] = name_out
                png_name = tex_cache[key]

        size = vmj.max(0) - vmj.min(0)
        report.append((mname, len(f), size, vmj.min(0), png_name, obj_name))

    print(f"{args.name}: {len(report)} 个材质分组")
    for mname, nf, size, lo, png, obj in sorted(report, key=lambda r: -r[1]):
        print(f"  {mname:<24s} 面 {nf:>7d}  尺寸 {size[0]:6.2f} x {size[1]:6.2f} x {size[2]:6.2f} m"
              f"  zmin {lo[2]:6.2f}  贴图 {'有' if png else '无'}")
    total = sum(r[1] for r in report)
    print(f"  合计 {total} 面；输出目录 props/imported/{args.name}/")


if __name__ == "__main__":
    main()
