"""观感修补：树减量+色相抖动、草簇缩放+加密+铺到房子边缘遮接缝、天空调亮。

    python polish.py --in ..\\demo_v19.xml --out ..\\demo_v20.xml

只做 XML 层面的改动，不重跑生成链，所以可以和 Codex 的整平/贴地脚本叠加使用。
"""
import argparse
import json
import math
import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def terrain_fn(model_xml):
    """从 XML 里读 hfield 参数，返回 f(x,y)->高度。经验：第 0 行 = -Y。"""
    import mujoco
    m = mujoco.MjModel.from_xml_path(model_xml)
    hid = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    fid = m.geom_dataid[hid]
    nr, nc = int(m.hfield_nrow[fid]), int(m.hfield_ncol[fid])
    sx, sy, sz, base = (float(v) for v in m.hfield_size[fid])
    h = np.asarray(m.hfield_data).reshape(nr, nc)
    px, py = float(m.geom_pos[hid][0]), float(m.geom_pos[hid][1])

    def f(x, y):
        fx = (x - px) / (2 * sx) + 0.5
        fy = (y - py) / (2 * sy) + 0.5
        if not (0 <= fx <= 1 and 0 <= fy <= 1):
            return None
        c, r = fx * (nc - 1), fy * (nr - 1)
        r0, c0 = int(r), int(c)
        r1, c1 = min(r0 + 1, nr - 1), min(c0 + 1, nc - 1)
        dr, dc = r - r0, c - c0
        v = (h[r0, c0] * (1 - dr) * (1 - dc) + h[r1, c0] * dr * (1 - dc)
             + h[r0, c1] * (1 - dr) * dc + h[r1, c1] * dr * dc)
        return base + float(v) * sz

    return f


def jitter_tree_colors(block, rng):
    """把树冠的绿色做一点色相/明度抖动，重复感会小很多。"""
    def repl(m):
        r, g, b = float(m.group(1)), float(m.group(2)), float(m.group(3))
        if g <= r or g <= b:          # 树干（棕色）不动
            return m.group(0)
        f = rng.uniform(0.82, 1.18)
        r2 = min(1.0, r * f * rng.uniform(0.9, 1.15))
        g2 = min(1.0, g * f)
        b2 = min(1.0, b * f * rng.uniform(0.85, 1.1))
        return f'rgba="{r2:.3f} {g2:.3f} {b2:.3f} 1"'
    return re.sub(r'rgba="([\d.]+) ([\d.]+) ([\d.]+) 1"', repl, block)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ASSETS, "demo_v19.xml"))
    ap.add_argument("--out", dest="dst", default=os.path.join(ASSETS, "demo_v20.xml"))
    ap.add_argument("--keep-trees", type=int, default=90)
    ap.add_argument("--grass-scale", type=float, default=0.40)
    ap.add_argument("--grass-count", type=int, default=110)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--ground-tex", action="store_true", help="地面换成 4096 版")
    args = ap.parse_args()

    xml = open(args.src, encoding="utf-8").read()
    rng = np.random.default_rng(args.seed)
    tz = terrain_fn(args.src)

    # ---------- 1. 程序化树：减量 + 色相抖动 ----------
    tree_re = re.compile(r'<body name="(tree_[^"]*)"[^>]*>.*?</body>', re.S)
    trees = list(tree_re.finditer(xml))
    if len(trees) > args.keep_trees:
        drop = set(rng.choice(len(trees), len(trees) - args.keep_trees, replace=False).tolist())
        out, last = [], 0
        for i, mt in enumerate(trees):
            out.append(xml[last:mt.start()])
            if i not in drop:
                out.append(jitter_tree_colors(mt.group(0), rng))
            last = mt.end()
        out.append(xml[last:])
        xml = "".join(out)
    else:
        xml = tree_re.sub(lambda m: jitter_tree_colors(m.group(0), rng), xml)
    print(f"trees: {len(trees)} -> {min(len(trees), args.keep_trees)}（色相已抖动）")

    # ---------- 2. 草簇：缩小 + 加密 ----------
    scale = args.grass_scale
    grass_re = re.compile(r'<body name="grass_(\d+)" pos="([-\d.]+) ([-\d.]+) ([-\d.]+)" euler="([^"]*)">'
                          r'<geom type="mesh" mesh="(gc\d+)" material="(gc\d+_mat)"[^>]*/></body>')
    base_grass = grass_re.findall(xml)
    # 先记下现有的 mesh/material 组合，再统一加 scale（顺序反了会把正则打断）
    meshes = sorted({g[5] for g in base_grass}) or ["gc0"]
    mats = sorted({g[6] for g in base_grass}) or ["gc0_mat"]
    # MJCF 的 geom 没有 scale 属性，缩放要写在共享的 <mesh scale="..."> 上（会作用于所有用它的地方）
    xml = re.sub(r'(<mesh name="gc\d+" file="[^"]+")',
                 rf'\1 scale="{scale} {scale} {scale}"', xml)
    print(f"grass: 现有 {len(base_grass)} 簇, 目标 {args.grass_count}, 缩放 {scale}")

    # 房子边缘一圈种草：遮住整平区和坡地的接缝
    plots = []
    cfgp = os.path.join(ASSETS, "buildings.json")
    if os.path.exists(cfgp):
        cfg = json.load(open(cfgp, encoding="utf-8"))
        plots = [p for p in cfg["plots"] if (p.get("model") or "").strip()]

    spots = []
    for p in plots:
        w, d = p["size"][0] / 2 + 1.6, p["size"][1] / 2 + 1.6
        a = math.radians(p["yaw"])
        for k in range(10):
            t = k / 10 * 2 * math.pi
            lx, ly = w * math.cos(t), d * math.sin(t)
            x = p["x"] + lx * math.cos(a) - ly * math.sin(a)
            y = p["y"] + lx * math.sin(a) + ly * math.cos(a)
            spots.append((x, y))

    meshes = sorted({g[5] for g in base_grass}) or ["gc0"]
    mats = sorted({g[6] for g in base_grass}) or ["gc0_mat"]
    added, idx = 0, len(base_grass)
    bodies = []
    while added < max(0, args.grass_count - len(base_grass)) and spots:
        x, y = spots.pop(int(rng.integers(len(spots))))
        z = tz(x, y)
        if z is None:
            continue
        k = int(rng.integers(len(meshes)))
        bodies.append(
            f'<body name="grass_{idx}" pos="{x:.2f} {y:.2f} {z + 0.02:.3f}" '
            f'euler="0 0 {rng.uniform(0, 360):.1f}">'
            f'<geom type="mesh" mesh="{meshes[k]}" material="{mats[k]}" '
            f'contype="0" conaffinity="0" group="1"/></body>')
        idx += 1
        added += 1
    xml = xml.replace("</worldbody>", "".join(bodies) + "</worldbody>", 1)
    print(f"grass: +{added} 簇（房子四周）")

    # ---------- 2.5 封路障碍 + 塌落堆积锥：在最终地形上摆，绕开 reground 的"抬飞邻居"问题 ----------
    rock_obj = "props/rocks/rock_07/rock_07_1k.obj"
    rock_tex = "props/rocks/rock_07/rock_07_1k_diffuse.png"
    have_rock = os.path.exists(os.path.join(ASSETS, rock_obj))
    asset_extra, rubble_bodies = [], []

    def rb_geom():
        if have_rock and rng.random() < 0.6:
            return (f'<geom type="mesh" mesh="rb_rock{int(rng.integers(3))}" '
                    f'material="rb_rock_mat" friction="1.1 0.02 0.001"/>')
        sx, sy, sz = (rng.uniform(0.3, 0.9) for _ in range(3))
        return (f'<geom type="box" size="{sx:.2f} {sy:.2f} {sz:.2f}" pos="0 0 {sz:.2f}" '
                f'material="brick" friction="1.1 0.02 0.001"/>')

    def drop(name, x, y, sink=0.06):
        z = tz(x, y)
        if z is None:
            return None
        return (f'<body name="{name}" pos="{x:.2f} {y:.2f} {z - sink:.3f}" '
                f'euler="0 0 {rng.uniform(0, 360):.1f}">{rb_geom()}</body>')

    if have_rock:
        # 岩石 OBJ 只有 0.14 m 高，放大 3/6/10 倍做出小中大三种块
        for i, sc in enumerate((3.0, 6.0, 10.0)):
            asset_extra.append(f'<mesh name="rb_rock{i}" file="{rock_obj}" scale="{sc} {sc} {sc}"/>')
        if os.path.exists(os.path.join(ASSETS, rock_tex)):
            asset_extra.append(f'<texture name="rb_rock_tex" type="2d" file="{rock_tex}"/>')
            asset_extra.append('<material name="rb_rock_mat" texture="rb_rock_tex" '
                               'specular="0.05" shininess="0.1"/>')
        else:
            asset_extra.append('<material name="rb_rock_mat" rgba="0.46 0.43 0.39 1"/>')

        for bi, b in enumerate(cfg.get("blockades") or []):
            for k in range(int(b.get("n", 10))):
                ang = rng.uniform(0, 2 * math.pi)
                rad = math.sqrt(rng.uniform(0, 1)) * float(b.get("radius", 3.0))
                bd = drop(f"blk_{bi}_{k}", b["x"] + rad * math.cos(ang),
                          b["y"] + rad * math.sin(ang))
                if bd:
                    rubble_bodies.append(bd)

        plot_by_id = {p["id"]: p for p in (cfg.get("plots") or [])}
        for c in cfg.get("debris_cones") or []:
            p = plot_by_id.get(c["plot"])
            if not p:
                continue
            half = math.hypot(p["size"][0], p["size"][1]) / 2
            for k in range(int(c.get("n", 22))):
                ang = rng.uniform(0, 2 * math.pi)
                dist = half + float(c.get("reach", 6.0)) * rng.random() ** 1.6
                bd = drop(f"debris_cone_{p['id']}_{k}",
                          p["x"] + dist * math.cos(ang), p["y"] + dist * math.sin(ang))
                if bd:
                    rubble_bodies.append(bd)

        if rubble_bodies:
            xml = xml.replace("</asset>", "".join(asset_extra) + "</asset>", 1)
            xml = xml.replace("</worldbody>", "".join(rubble_bodies) + "</worldbody>", 1)
            print(f"rubble: {len(rubble_bodies)} 块（封路 + 塌落堆积锥，落在最终地形）")

    # ---------- 3. 天空：地平线提亮，远山不那么"贴纸" ----------
    xml = re.sub(r'rgb1="[^"]*"', 'rgb1="0.42 0.56 0.72"', xml, count=1)
    xml = re.sub(r'rgb2="[^"]*"', 'rgb2="0.80 0.86 0.92"', xml, count=1)

    # ---------- 4. 地面换高清烘焙图（2048 -> 4096，5 cm/px） ----------
    hd = os.path.join(ASSETS, "tex", "ground_baked_hd.png")
    if args.ground_tex and os.path.exists(hd):
        xml = re.sub(r'name="gtex" type="2d" file="[^"]*"',
                     'name="gtex" type="2d" file="tex/ground_baked_hd.png"', xml)
        print(f"ground: -> tex/ground_baked_hd.png ({os.path.getsize(hd)/1e6:.1f} MB)")

    open(args.dst, "w", encoding="utf-8").write(xml)
    print(f"wrote {os.path.relpath(args.dst, ASSETS)}")


if __name__ == "__main__":
    main()
