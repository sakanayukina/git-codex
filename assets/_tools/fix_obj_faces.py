r"""检查 / 修复 OBJ 面索引被写成 "f a/b/c"（三顶点被挤成 v/vt/vn）的坏文件。

    python fix_obj_faces.py --check     # 只报告
    python fix_obj_faces.py --fix       # 就地修复
"""
import argparse
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def scan(path):
    """返回 (坏面数, 好面数)。坏面形如 'f 132/130/111'（单组、三个数）。"""
    bad = good = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for ln in fh:
            if not ln.startswith("f "):
                continue
            groups = ln.split()[1:]
            if len(groups) >= 3:
                good += 1
            else:
                bad += 1
    return bad, good


def repair(path):
    tmp = path + ".tmp"
    bad, good = scan(path)
    if bad == 0:
        return 0, good
    with open(path, "r", encoding="utf-8", errors="ignore") as src, \
            open(tmp, "w", encoding="utf-8") as dst:
        for ln in src:
            if ln.startswith("f "):
                groups = ln.split()[1:]
                if len(groups) < 3:
                    parts = groups[0].split("/")
                    if len(parts) != 3:
                        continue
                    a, b, c = parts
                    dst.write(f"f {a}/{a} {b}/{b} {c}/{c}\n")
                    continue
            dst.write(ln)
    os.replace(tmp, path)
    return bad, good


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    objs = sorted(glob.glob(os.path.join(ASSETS, "props", "**", "*.obj"), recursive=True)
                  + glob.glob(os.path.join(ASSETS, "generated", "*.obj"), recursive=True))
    total_bad = 0
    for p in objs:
        bad, good = scan(p)
        rel = os.path.relpath(p, ASSETS)
        if bad == 0:
            print(f"  ok    {rel:70s} faces={good}")
            continue
        total_bad += bad
        if args.fix:
            repair(p)
            bad2, good2 = scan(p)
            print(f"  FIXED {rel:70s} bad {bad} -> {bad2}, faces now {good2}")
        else:
            print(f"  BAD   {rel:70s} bad={bad} good={good}")
    print(f"\n{'fix 完成' if args.fix else '需要修复'}: {total_bad} 个坏面")


if __name__ == "__main__":
    main()
