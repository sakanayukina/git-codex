r"""导入本地下载的 Sketchfab / 通用 glTF 模型（.gltf 或 .glb）-> MuJoCo 可用的 OBJ + PNG。

    python import_gltf.py --src ..\incoming\maple\maple.glb --name maple --target-height 8

做的事：
1. .glb 拆成 .gltf + .bin（顺手把内嵌贴图导成文件）
2. data: URI 的 buffer / 贴图也一并落盘
3. 复用 fetch_ph_model.convert() 展平场景图、Z-up、可选减面
4. 输出 <name>.obj / <name>.mtl / <name>_diffuse.png，并打印尺寸与面数
"""
import argparse
import base64
import json
import os
import shutil
import struct
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import fetch_ph_model as fpm  # noqa: E402


def unpack_glb(path, out_dir, stem):
    """把 .glb 拆成 <stem>.gltf + <stem>.bin，返回 gltf 路径。"""
    with open(path, "rb") as f:
        magic, version, length = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:
            raise SystemExit("不是合法的 GLB（magic 不对）")
        js = bin_chunk = None
        while f.tell() < length:
            clen, ctype = struct.unpack("<II", f.read(8))
            data = f.read(clen)
            if ctype == 0x4E4F534A:
                js = data
            elif ctype == 0x004E4942:
                bin_chunk = data
    if js is None:
        raise SystemExit("GLB 里没有 JSON chunk")
    gltf = json.loads(js.decode("utf-8"))

    os.makedirs(out_dir, exist_ok=True)
    if bin_chunk:
        open(os.path.join(out_dir, f"{stem}.bin"), "wb").write(bin_chunk)
        for b in gltf.get("buffers", []):
            if "uri" not in b:
                b["uri"] = f"{stem}.bin"
    gltf_path = os.path.join(out_dir, f"{stem}.gltf")
    json.dump(gltf, open(gltf_path, "w", encoding="utf-8"))
    return gltf_path, gltf


def materialize(gltf, model_dir, stem):
    """data: URI 的 buffer 和贴图落盘，保证 read_accessor / convert 能按文件名读。"""
    changed = False
    for i, b in enumerate(gltf.get("buffers", [])):
        uri = b.get("uri", "")
        if uri.startswith("data:"):
            blob = base64.b64decode(uri.split(",", 1)[1])
            name = f"{stem}_buf{i}.bin"
            open(os.path.join(model_dir, name), "wb").write(blob)
            b["uri"] = name
            changed = True

    for i, img in enumerate(gltf.get("images", [])):
        uri = img.get("uri", "")
        if uri.startswith("data:"):
            head, payload = uri.split(",", 1)
            ext = ".png" if "png" in head else ".jpg"
            blob = base64.b64decode(payload)
            name = f"tex{i}{ext}"
            open(os.path.join(model_dir, name), "wb").write(blob)
            img["uri"] = name
            changed = True
        elif uri:
            img["uri"] = urllib.parse.unquote(uri)

    if changed:
        json.dump(gltf, open(os.path.join(model_dir, f"{stem}.gltf"), "w", encoding="utf-8"))
    return gltf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--target-height", type=float, default=0.0)
    ap.add_argument("--max-tris", type=int, default=0)
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        raise SystemExit(f"路径不存在：{src}")
    ext = os.path.splitext(src)[1].lower()
    if ext not in (".glb", ".gltf"):
        raise SystemExit(f"只吃 .glb / .gltf，收到 {ext}")

    model_dir = os.path.join(ASSETS, "props", "imported", args.name)
    os.makedirs(model_dir, exist_ok=True)
    stem = args.name

    if ext == ".glb":
        gltf_path, gltf = unpack_glb(src, model_dir, stem)
        print(f"GLB 已拆分 -> {os.path.basename(gltf_path)}")
    else:
        shutil.copy2(src, os.path.join(model_dir, f"{stem}.gltf"))
        for f in os.listdir(os.path.dirname(src)):           # 顺带搬走同目录的 bin 和贴图
            if f.lower().endswith((".bin", ".png", ".jpg", ".jpeg")):
                shutil.copy2(os.path.join(os.path.dirname(src), f), os.path.join(model_dir, f))
        gltf_path = os.path.join(model_dir, f"{stem}.gltf")
        gltf = json.load(open(gltf_path, encoding="utf-8"))

    gltf = materialize(gltf, model_dir, stem)
    if any("draco" in str(e).lower() for e in gltf.get("extensionsUsed", [])):
        raise SystemExit("这个模型用了 Draco 压缩，转换器不支持——请回网站换 .gltf（非 Draco）或 .dae")

    obj, png = fpm.convert(model_dir, stem, args.max_tris)

    # 量尺寸（顺便给缩放建议）
    import numpy as np
    v = np.array([[float(x) for x in ln.split()[1:4]] for ln in open(obj) if ln.startswith("v ")])
    size = v.max(0) - v.min(0)
    print(f"\n{args.name}: 尺寸 {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} m, 底面 z={v.min(0)[2]:.2f}")
    if args.target_height and size[2] > 1e-6:
        s = args.target_height / size[2]
        print(f"  建议 model_scale = {s:.4f}（高度 {args.target_height} m）")
    print(f"  输出: {os.path.relpath(obj, ASSETS)}")


if __name__ == "__main__":
    main()
