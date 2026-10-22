r"""工作区清理：删临时图/中间产物/缓存，保留可复现的最小集合。

    python cleanup.py            # 只报告
    python cleanup.py --apply    # 真删
"""
import argparse
import glob
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
ROOT = os.path.dirname(ASSETS)

# 要保留的展示图
KEEP_PNGS = {"_v6_h1.png"}
# 中间版本 XML（v5 是 village.py 的 base，必须留；v6 是当前场景）
KEEP_XML = {"demo_v5.xml", "demo_v6.xml", "demo_rescue_scene.xml"}


def size_of(paths):
    total = 0
    for p in paths:
        if os.path.isfile(p):
            total += os.path.getsize(p)
        elif os.path.isdir(p):
            for cur, _d, fs in os.walk(p):
                for f in fs:
                    try:
                        total += os.path.getsize(os.path.join(cur, f))
                    except OSError:
                        pass
    return total


def collect():
    targets = []

    # 1) assets 根下的一次性预览图
    for p in glob.glob(os.path.join(ASSETS, "_*.png")):
        if os.path.basename(p) not in KEEP_PNGS:
            targets.append(p)
    # 2) 中间版本 XML
    for p in glob.glob(os.path.join(ASSETS, "demo_*.xml")):
        if os.path.basename(p) not in KEEP_XML:
            targets.append(p)
    # 3) 论文参考图（一次性的）
    refs = os.path.join(ASSETS, "_refs")
    if os.path.isdir(refs):
        targets.append(refs)
    # 4) Python 缓存
    for cur, dirs, _f in os.walk(ROOT):
        if "__pycache__" in dirs:
            targets.append(os.path.join(cur, "__pycache__"))
            dirs.remove("__pycache__")
    # 5) 仓库根的下载包（已解压进 incoming）
    targets.extend(glob.glob(os.path.join(ROOT, "*.zip")))
    return targets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total_before = size_of([ROOT])
    targets = collect()
    print(f"workspace before: {total_before/1e6:.1f} MB")
    print(f"to delete: {len(targets)} items")
    for p in sorted(targets, key=lambda x: -size_of([x]))[:20]:
        print(f"  {size_of([p])/1e6:7.2f} MB  {os.path.relpath(p, ROOT)}")

    if not args.apply:
        print("\n(dry run; rerun with --apply)")
        return

    freed = size_of(targets)
    for p in targets:
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        except OSError as e:
            print(f"  ! skip {os.path.relpath(p, ROOT)}: {e}")
    total_after = size_of([ROOT])
    print(f"\nfreed {freed/1e6:.1f} MB, workspace now {total_after/1e6:.1f} MB")


if __name__ == "__main__":
    main()
