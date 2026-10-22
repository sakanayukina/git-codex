r"""岩石瘦身：场景里 122 个高模石头占了 6.3 M 三角面，按距离保留一批、丢掉其余。

    python slim_rocks.py                  # 只报告
    python slim_rocks.py --apply          # 写 demo_v6_slim.xml
    python slim_rocks.py --apply --in-place   # 直接覆盖 demo_v6.xml（会留 .bak）

策略：保留离村庄中心最近的 N 个 + 名字带 _hero_ 的，其余删除。
输出只打印几行（面数前后对比），方便快速迭代。
"""
import argparse
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)

ROCK_RE = re.compile(
    r'<body name="(rk_x\d+|boulder_01_\d+|rock_07_\d+|rock_moss_set_01_\d+)" '
    r'pos="([-\d.]+) ([-\d.]+) [-\d.]+"[^>]*>.*?</body>', re.S)
MESH_RE = re.compile(r'<mesh name="([^"]+)" file="([^"]+)"')
GEOM_RE = re.compile(r'<geom[^>]*type="mesh"[^>]*mesh="([^"]+)"')
GEOM_RE2 = re.compile(r'<geom[^>]*mesh="([^"]+)"[^>]*type="mesh"')


def face_count(rel_path, cache={}):
    if rel_path in cache:
        return cache[rel_path]
    p = os.path.join(ASSETS, rel_path)
    n = 0
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for ln in f:
                if ln.startswith("f "):
                    n += 1
    except OSError:
        n = 0
    cache[rel_path] = n
    return n


def total_tris(xml):
    mesh_faces = {name: face_count(path) for name, path in MESH_RE.findall(xml)}
    total = 0
    for name in GEOM_RE.findall(xml) + GEOM_RE2.findall(xml):
        total += mesh_faces.get(name, 0)
    return total, len(GEOM_RE.findall(xml)) + len(GEOM_RE2.findall(xml))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ASSETS, "demo_v6.xml"))
    ap.add_argument("--out", dest="dst", default=os.path.join(ASSETS, "demo_v6_slim.xml"))
    ap.add_argument("--keep", type=int, default=40)
    ap.add_argument("--focus", default="10,-6", help="保留离这个点最近的 N 个石头")
    ap.add_argument("--drop-grass", action="store_true", help="同时删掉扁平的草皮/苔藓实例")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--in-place", action="store_true")
    args = ap.parse_args()

    xml = open(args.src, encoding="utf-8").read()
    fx, fy = [float(v) for v in args.focus.split(",")]

    if args.drop_grass:
        grass_re = re.compile(r'<body name="(?:grass_medium_01|moss_01)_\d+"[^>]*>.*?</body>', re.S)
        n_grass = len(grass_re.findall(xml))
        xml = grass_re.sub("", xml)
        print(f"dropped grass/moss instances: {n_grass}")

    rocks = []
    for m in ROCK_RE.finditer(xml):
        name, x, y = m.group(1), float(m.group(2)), float(m.group(3))
        dist = ((x - fx) ** 2 + (y - fy) ** 2) ** 0.5
        hero = "_hero_" in name
        rocks.append((hero, dist, name, m.group(0)))

    before, _ = total_tris(xml)
    print(f"rocks: {len(rocks)}   tris total: {before/1e6:.2f} M")

    rocks.sort(key=lambda r: (not r[0], r[1]))      # hero 优先，其次近处
    keep = rocks[:args.keep]
    drop = rocks[args.keep:]
    for _h, _d, _n, block in drop:
        xml = xml.replace(block, "")

    after, _ = total_tris(xml)
    print(f"keep {len(keep)} / drop {len(drop)}")
    print(f"tris after: {after/1e6:.2f} M  (saved {(before-after)/1e6:.2f} M)")

    if not args.apply:
        print("(dry run; add --apply)")
        return
    out = args.src if args.in_place else args.dst
    if args.in_place:
        open(args.src + ".bak", "w", encoding="utf-8").write(open(args.src, encoding="utf-8").read())
    open(out, "w", encoding="utf-8").write(xml)
    print(f"wrote {os.path.relpath(out, ASSETS)}")


if __name__ == "__main__":
    main()
