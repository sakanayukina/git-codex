r"""把下载来的建筑模型接进场景：检查 → 归一化 → 生成 MJCF 片段 → 可选写回 buildings.json。

你只需要把模型（OBJ + 贴图）丢到 assets/incoming/<随便>/ 下，然后：

    python import_building.py --src ../incoming/my_ruin --name ruin_01
    python import_building.py --src ../incoming/my_ruin --name ruin_01 --target-height 6 --plot H2

做的事：
1. 找主 .obj（最大的那个），量尺寸、数面数，给出体检报告
2. 贴图 jpg → png（MuJoCo 只认 png/jpg，但 png 最稳）
3. 按 --target-height 或 --scale 归一化，写一份 <name>.mtl 与 snippet.xml
4. --plot 时直接改 buildings.json 里那栋房的 model 字段
"""
import argparse
import glob
import json
import os
import shutil

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
BUILDINGS = os.path.join(ASSETS, "props", "buildings")


def find_obj(src):
    objs = glob.glob(os.path.join(src, "**", "*.obj"), recursive=True)
    if not objs:
        raise SystemExit(f"没找到 .obj：{src}\n"
                         "  FBX/GLB 需要先转 OBJ：Blender 打开 → 导出 Wavefront (.obj)，勾选 贴图/UV")
    objs.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return objs[0]


def find_diffuse(src):
    pats = ("*diff*", "*albedo*", "*basecolor*", "*base_color*", "*color*", "*d.[jp][pn]g")
    for pat in pats:
        for ext in (".png", ".jpg", ".jpeg", ".PNG", ".JPG"):
            hits = glob.glob(os.path.join(src, "**", pat + ext), recursive=True)
            if hits:
                return max(hits, key=os.path.getsize)
    # 再退一步：目录里最大的图片
    imgs = [p for e in ("png", "jpg", "jpeg", "PNG", "JPG")
            for p in glob.glob(os.path.join(src, "**", f"*.{e}"), recursive=True)]
    return max(imgs, key=os.path.getsize) if imgs else None


def obj_stats(path):
    v, f = [], 0
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for ln in fh:
            if ln.startswith("v "):
                v.append([float(x) for x in ln.split()[1:4]])
            elif ln.startswith("f "):
                f += max(0, len(ln.split()) - 3)
    a = np.asarray(v)
    return a.min(0), a.max(0), len(a), f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="下载解压后的目录（或直接给 .obj）")
    ap.add_argument("--name", required=True, help="资产名，如 ruin_01")
    ap.add_argument("--target-height", type=float, default=0.0, help="按高度等比缩放（米）")
    ap.add_argument("--scale", type=float, default=0.0, help="直接给缩放系数（优先于 target-height）")
    ap.add_argument("--plot", default="", help="写回 buildings.json 的房号，如 H2")
    args = ap.parse_args()

    src = args.src if not os.path.isabs(args.src) else args.src
    if not os.path.exists(src):
        raise SystemExit(f"路径不存在：{src}")
    obj = src if src.lower().endswith(".obj") else find_obj(src)
    root = os.path.dirname(obj)
    lo, hi, nv, nf = obj_stats(obj)
    size = hi - lo
    print(f"模型: {obj}")
    print(f"  顶点 {nv}  三角面 {nf}")
    print(f"  尺寸 {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} m")
    print(f"  底面 z = {lo[2]:.2f}，中心 x/y = {(lo[0] + hi[0]) / 2:.2f} / {(lo[1] + hi[1]) / 2:.2f}")

    # 体检
    warn = []
    if nf > 250_000:
        warn.append(f"面数 {nf} 偏高（>25 万），MuJoCo 渲染会明显掉帧")
    if min(size[:2]) < 0.3:
        warn.append("某一维小于 0.3 m，可能是单面片或单位不对")
    if abs(lo[2]) > 1.0:
        warn.append(f"模型底面不在 z=0（{lo[2]:.2f}），接入时会自动抬到地面")
    # cm 单位启发：一栋房子要是 800 多，基本是厘米
    if max(size[:2]) > 60:
        warn.append(f"尺寸 {max(size[:2]):.0f} 像厘米单位（1 m 的 100 倍），建议 --scale 0.01")
    for w in warn:
        print("  ⚠", w)

    scale = args.scale or (args.target_height / size[2] if args.target_height and size[2] > 1e-6 else 1.0)
    if scale != 1.0:
        print(f"  缩放系数 {scale:.4f} → 目标尺寸 "
              f"{size[0] * scale:.2f} x {size[1] * scale:.2f} x {size[2] * scale:.2f} m")

    # 归档
    dst = os.path.join(BUILDINGS, args.name)
    os.makedirs(dst, exist_ok=True)
    shutil.copy2(obj, os.path.join(dst, f"{args.name}.obj"))

    tex_rel = ""
    raw_tex = find_diffuse(root)
    if raw_tex:
        tex_rel = f"props/buildings/{args.name}/{args.name}_diffuse.png"
        Image.open(raw_tex).convert("RGB").save(os.path.join(dst, f"{args.name}_diffuse.png"))
        print(f"  贴图 {os.path.basename(raw_tex)} → {os.path.basename(tex_rel)}")
    else:
        print("  ⚠ 没找到颜色贴图，将用纯色材质")

    with open(os.path.join(dst, f"{args.name}.mtl"), "w", encoding="utf-8") as f:
        f.write(f"newmtl {args.name}\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nd 1\nillum 1\n")
        if tex_rel:
            f.write(f"map_Kd {os.path.basename(tex_rel)}\n")

    sc = f' scale="{scale} {scale} {scale}"' if scale != 1.0 else ""
    snip = (f'<mesh name="{args.name}" file="props/buildings/{args.name}/{args.name}.obj"{sc}/>\n'
            f'<material name="{args.name}_mat" ' +
            (f'texture="{args.name}_tex"' if tex_rel else 'rgba="0.62 0.60 0.56 1"') + '/>\n'
            + (f'<texture name="{args.name}_tex" type="2d" file="{tex_rel}"/>\n' if tex_rel else ""))
    with open(os.path.join(dst, "snippet.xml"), "w", encoding="utf-8") as f:
        f.write(snip)
    print(f"  写入 {os.path.relpath(dst, ASSETS)}/（obj + png + mtl + snippet.xml）")

    if args.plot:
        cfg_path = os.path.join(ASSETS, "buildings.json")
        cfg = json.load(open(cfg_path, encoding="utf-8"))
        hit = [p for p in cfg["plots"] if p["id"] == args.plot]
        if not hit:
            raise SystemExit(f"buildings.json 里没有 {args.plot}")
        hit[0]["model"] = f"props/buildings/{args.name}/{args.name}.obj"
        hit[0]["model_scale"] = round(scale, 4)
        json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  ✅ 已把 {args.plot} 的 model 指向 {args.name}（重跑 village.py 生效）")


if __name__ == "__main__":
    main()
