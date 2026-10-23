r"""清掉 props/imported 下转换后不再需要的中间文件（.gltf/.bin/原始贴图副本）。

    python prune_imported.py            # 只报告
    python prune_imported.py --apply    # 真删
"""
import argparse
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
IMPORTED = os.path.join(ASSETS, "props", "imported")

# 这些是转换的输入，不是运行时需要的
DROP_EXT = {".gltf", ".bin"}


def plan():
    todos, keep_bytes, drop_bytes = [], 0, 0
    for name in sorted(os.listdir(IMPORTED)):
        d = os.path.join(IMPORTED, name)
        if not os.path.isdir(d):
            continue
        files = os.listdir(d)
        has_atlas = any("atlas" in f and f.endswith(".png") for f in files)
        for f in files:
            p = os.path.join(d, f)
            size = os.path.getsize(p)
            ext = os.path.splitext(f)[1].lower()
            drop = ext in DROP_EXT
            # 转换时从 GLB 抽出来的原始贴图（tex0.png 等），有 atlas 就可以删
            if has_atlas and f.startswith("tex") and ext in (".png", ".jpg", ".jpeg"):
                drop = True
            # normal / occlusion / metallicRoughness 在 MuJoCo 3.3.2 完全不用（没有 PBR），
            # 但这些原图常有 8K、几十 MB，留着纯占地方
            low = f.lower()
            if any(k in low for k in ("_normal", "_occlusion", "metallicroughness", "_rough", "_metallic")):
                drop = True
            # 有 atlas 之后，原始 baseColor/diffuse 大图也多余（atlas 就是从它们压出来的）
            if has_atlas and ("basecolor" in low or "diffuse" in low) and ext in (".png", ".jpg", ".jpeg"):
                drop = True
            if drop:
                todos.append(p)
                drop_bytes += size
            else:
                keep_bytes += size
    return todos, keep_bytes, drop_bytes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    todos, keep, drop = plan()
    print(f"imported: keep {keep/1e6:.1f} MB, drop {drop/1e6:.1f} MB ({len(todos)} files)")
    for p in sorted(todos, key=os.path.getsize, reverse=True)[:8]:
        print(f"  {os.path.getsize(p)/1e6:7.1f} MB  {os.path.relpath(p, ASSETS)}")
    if not args.apply:
        print("(dry run; add --apply)")
        return
    for p in todos:
        try:
            os.remove(p)
        except OSError as e:
            print("  !", p, e)
    print(f"freed {drop/1e6:.1f} MB")


if __name__ == "__main__":
    main()
