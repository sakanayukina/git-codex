r"""在现有场景上加密植被、石头、草，并加一栋半塌的乡村房屋。

    python scatter.py --in ..\demo_v4.xml --out ..\demo_v5.xml

分工：build_scene.py 负责地形与原始布点，本脚本只在 <worldbody> 末尾追加内容，
不覆盖别人的文件。房屋是程序化拼的（墙段 + 窗洞 + 塌墙 + 楼板 + 室内碎块），
比单纯堆方块像建筑。
"""
import argparse
import math
import os
import re

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


class Terrain:
    """与 build_scene.py 保持同一套映射：h = base + px/255 * relief，行 0 = +Y。"""

    def __init__(self, png, extent, relief, base):
        g = np.asarray(Image.open(png).convert("L"), dtype=np.float64)
        self.z = g / 255.0 * relief
        self.nrow, self.ncol = self.z.shape
        self.extent, self.relief, self.base = extent, relief, base

    def height(self, x, y):
        fx = (x + self.extent / 2) / self.extent * (self.ncol - 1)
        fy = (self.extent / 2 - y) / self.extent * (self.nrow - 1)
        x0, y0 = int(np.clip(np.floor(fx), 0, self.ncol - 1)), int(np.clip(np.floor(fy), 0, self.nrow - 1))
        x1, y1 = min(x0 + 1, self.ncol - 1), min(y0 + 1, self.nrow - 1)
        dx, dy = fx - x0, fy - y0
        z = self.z
        v = (z[y0, x0] * (1 - dx) * (1 - dy) + z[y0, x1] * dx * (1 - dy)
             + z[y1, x0] * (1 - dx) * dy + z[y1, x1] * dx * dy)
        return self.base + v

    def slope(self, x, y, eps=2.0):
        return math.hypot(self.height(x + eps, y) - self.height(x - eps, y),
                          self.height(x, y + eps) - self.height(x, y - eps)) / (2 * eps)


def find_terrain(xml):
    m = re.search(r'<hfield[^>]*file="([^"]+)"[^>]*size="([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"', xml)
    if not m:
        raise SystemExit("no hfield found")
    return m.group(1), float(m.group(2)) * 2, float(m.group(4)), float(m.group(5))


def rock_meshes(xml):
    """Existing rock mesh assets: [(name, file, scale)]."""
    out = []
    for m in re.finditer(r'<mesh name="([^"]+)" file="(props/rocks/[^"]+)"(?: scale="([\d.]+) [\d.]+ [\d.]+")?', xml):
        out.append((m.group(1), m.group(2), float(m.group(3) or 1.0)))
    return out


def grass_mesh(xml):
    m = re.search(r'<mesh name="([^"]+)" file="(props/ground/[^"]+)"', xml)
    return (m.group(1), m.group(2)) if m else (None, None)


def conifer_body(name, x, y, z, h, rng, tint):
    parts = [f'<body name="{name}" pos="{x:.2f} {y:.2f} {z:.3f}" '
             f'euler="{rng.uniform(-4, 4):.1f} {rng.uniform(-4, 4):.1f} {rng.uniform(0, 360):.1f}">']
    trunk_h = h * rng.uniform(0.14, 0.22)
    parts.append(f'<geom type="cylinder" size="{0.022 * h:.3f} {trunk_h / 2:.3f}" '
                 f'pos="0 0 {trunk_h / 2:.3f}" rgba="0.24 0.17 0.11 1"/>')
    tiers = [(0.20, 0.245, 0.27), (0.42, 0.185, 0.23), (0.62, 0.135, 0.19), (0.80, 0.075, 0.15)]
    for c, r, hr in tiers:
        g = tint * rng.uniform(0.82, 1.12)
        parts.append(f'<geom type="ellipsoid" size="{r * h * rng.uniform(0.85, 1.15):.3f} '
                     f'{r * h * rng.uniform(0.85, 1.15):.3f} {hr * h:.3f}" '
                     f'pos="0 0 {c * h:.3f}" rgba="{g[0]:.3f} {g[1]:.3f} {g[2]:.3f} 1" '
                     f'contype="0" conaffinity="0" group="1"/>')
    parts.append("</body>")
    return "".join(parts)


def house(cx, cy, t, rng, yaw_deg=18.0):
    """一栋 8.4 x 6.2 m、墙高 3 m 的半塌砖房：窗洞、塌角、倒下的楼板、室内碎块。"""
    gz = t.height(cx, cy)
    W, D, H, th = 8.4, 6.2, 3.0, 0.22
    a = math.radians(yaw_deg)
    ca, sa = math.cos(a), math.sin(a)

    def loc(u, v):
        """局部坐标 (u 沿墙宽, v 沿进深) -> 世界 xy"""
        return cx + u * ca - v * sa, cy + u * sa + v * ca

    out = [f'<body name="house" pos="{cx:.2f} {cy:.2f} {gz:.3f}" euler="0 0 {yaw_deg}">']
    mat = ' material="brick"'
    mat_floor = ' material="concrete"'
    # 地基
    out.append(f'<geom type="box" size="{W / 2 + 0.3:.2f} {D / 2 + 0.3:.2f} 0.15" '
               f'pos="0 0 0.12"{mat_floor}/>')

    # 四面墙：分段留窗洞/门洞；西墙塌掉一半
    def wall(u0, u1, v, h0, h1, tilt=0.0):
        w = (u1 - u0) / 2
        out.append(f'<geom type="box" size="{w:.2f} {th / 2:.2f} {(h1 - h0) / 2:.2f}" '
                   f'pos="{(u0 + u1) / 2:.2f} {v:.2f} {(h0 + h1) / 2 + 0.15:.2f}" '
                   f'euler="0 {tilt:.1f} 0"{mat}/>')

    # 北墙：整段 + 两个窗下墙
    wall(-W / 2, W / 2, D / 2, 0.0, 1.05)          # 窗下
    wall(-W / 2, W / 2, D / 2, 2.05, H)            # 窗上
    wall(-W / 2, -W / 2 + 1.0, D / 2, 1.05, 2.05)  # 左侧窗间柱
    wall(W / 2 - 1.0, W / 2, D / 2, 1.05, 2.05)
    wall(-0.9, 0.9, D / 2, 1.05, 2.05)
    # 南墙：门洞
    wall(-W / 2, -1.1, -D / 2, 0.0, H)
    wall(1.1, W / 2, -D / 2, 0.0, H)
    wall(-1.1, 1.1, -D / 2, 2.1, H)
    # 东墙：两段，靠北一段塌了（矮 + 倾斜）
    wall(W / 2, W / 2, -D / 2, 0.0, H) if False else None
    out.append(f'<geom type="box" size="{th / 2:.2f} {D / 4:.2f} {H / 2:.2f}" '
               f'pos="{W / 2:.2f} {-D / 4:.2f} {H / 2 + 0.15:.2f}"{mat}/>')
    out.append(f'<geom type="box" size="{th / 2:.2f} {D / 5:.2f} 0.75" '
               f'pos="{W / 2:.2f} {D / 3:.2f} {0.9:.2f}" euler="0 -9 0"{mat}/>')
    # 西墙：只剩半截 + 一堆塌下的砖（用小块堆叠）
    out.append(f'<geom type="box" size="{th / 2:.2f} {D / 3:.2f} 0.55" '
               f'pos="{-W / 2:.2f} {-D / 3:.2f} {0.7:.2f}"{mat}/>')
    for i in range(26):
        bu = rng.uniform(-W / 2 - 1.2, -W / 2 + 0.6)
        bv = rng.uniform(-D / 2, D / 2)
        s1, s2, s3 = rng.uniform(0.12, 0.28), rng.uniform(0.08, 0.2), rng.uniform(0.1, 0.3)
        out.append(f'<geom type="box" size="{s1:.3f} {s2:.3f} {s3:.3f}" '
                   f'pos="{bu:.2f} {bv:.2f} {rng.uniform(0.2, 1.1):.2f}" '
                   f'euler="{rng.uniform(-30, 30):.0f} {rng.uniform(-30, 30):.0f} {rng.uniform(0, 360):.0f}" '
                   f'rgba="0.42 0.40 0.37 1"/>')

    # 屋顶：两块塌落楼板（静态，斜插进废墟里）
    out.append(f'<geom type="box" size="{W / 2.6:.2f} {D / 2.6:.2f} 0.11" '
               f'pos="{-0.4:.2f} {1.1:.2f} {2.55:.2f}" euler="26 -6 14"{mat_floor}/>')
    out.append(f'<geom type="box" size="{W / 3.2:.2f} {D / 3.4:.2f} 0.10" '
               f'pos="{1.6:.2f} {2.4:.2f} {0.45:.2f}" euler="-14 8 -30"{mat_floor}/>')
    # 室内碎块
    for i in range(40):
        u, v = rng.uniform(-W / 2 + 0.4, W / 2 - 0.4), rng.uniform(-D / 2 + 0.4, D / 2 - 0.4)
        s = rng.uniform(0.06, 0.2)
        out.append(f'<geom type="box" size="{s:.3f} {s * 1.4:.3f} {s * 0.6:.3f}" '
                   f'pos="{u:.2f} {v:.2f} {rng.uniform(0.15, 0.75):.2f}" '
                   f'euler="{rng.uniform(0, 360):.0f} {rng.uniform(0, 360):.0f} {rng.uniform(0, 360):.0f}" '
                   f'rgba="0.46 0.44 0.41 1"/>')
    out.append("</body>")
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ASSETS, "demo_v4.xml"))
    ap.add_argument("--out", dest="dst", default=os.path.join(ASSETS, "demo_v5.xml"))
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    xml = open(args.src, encoding="utf-8").read()
    # 清掉 bark_debris 这类薄片：锚不住、贴地后像散落的钢筋，很出戏
    xml = re.sub(r'<body name="bark_debris[^"]*"[^>]*>.*?</body>', "", xml, flags=re.S)
    png_rel, extent, relief, base = find_terrain(xml)
    t = Terrain(os.path.join(ASSETS, png_rel), extent, relief, base)
    rng = np.random.default_rng(args.seed)

    rocks = rock_meshes(xml)
    gmesh, gfile = grass_mesh(xml)
    print(f"terrain {extent:.0f} m, relief {relief:.1f} m; rocks={len(rocks)} grass={'yes' if gmesh else 'no'}")

    # 石头的多个尺寸变体（每种 2 档）
    new_assets = []
    variants = []
    for i, (nm, f, sc) in enumerate(rocks):
        for k, mult in enumerate((0.55, 1.25)):
            vn = f"rs{i}_{k}"
            new_assets.append(f'<mesh name="{vn}" file="{f}" scale="{sc * mult:.3f} {sc * mult:.3f} {sc * mult:.3f}"/>')
            variants.append(vn)

    # 砖墙材质（墙用砖、楼板用混凝土）
    new_assets.append('<texture name="brick_tex" type="2d" file="tex/brick_wall_001_diffuse.png"/>')
    new_assets.append('<material name="brick" texture="brick_tex" texrepeat="4 2" '
                      'texuniform="true" rgba="0.72 0.66 0.60 1" specular="0.04" shininess="0.1"/>')
    xml = xml.replace("<hfield name=", "".join(new_assets) + "\n    <hfield name=", 1)
    new_assets = []

    body, placed = [], []
    cx, cy = 10.0, -6.0          # 原有废墟中心
    hx, hy = 2.0, -24.0          # 房屋位置

    def ok(x, y, min_slope=1.3):
        return t.slope(x, y) < min_slope

    def far(x, y, d):
        return (x - cx) ** 2 + (y - cy) ** 2 > d * d and (x - hx) ** 2 + (y - hy) ** 2 > d * d

    # ---- 房子
    body.append(house(hx, hy, t, rng))
    print(f"house at ({hx}, {hy}) ground z = {t.height(hx, hy):.2f}")

    # ---- 密林：成簇分布，近处更密
    half = extent / 2 - 8
    n_tree = 90
    clusters = [rng.uniform(-half, half, 2) for _ in range(7)]
    added = 0
    for _ in range(n_tree * 8):
        if added >= n_tree:
            break
        if rng.random() < 0.72:
            bx, by = clusters[rng.integers(len(clusters))]
            x, y = bx + rng.normal(0, 9), by + rng.normal(0, 9)
        else:
            x, y = rng.uniform(-half, half, 2)
        if abs(x) > half or abs(y) > half or not ok(x, y) or not far(x, y, 7.0):
            continue
        if any((x - a) ** 2 + (y - b) ** 2 < 2.2 ** 2 for a, b in placed):
            continue
        placed.append((x, y))
        h = rng.uniform(6.5, 16.0)
        body.append(conifer_body(f"tree_x{added}", x, y, t.height(x, y), h, rng,
                                 np.array([0.075, 0.20, 0.085])))
        added += 1

    # ---- 石头：密集但小的多，大的少
    n_rock = 110
    added = 0
    for _ in range(n_rock * 6):
        if added >= n_rock:
            break
        x, y = rng.uniform(-half, half, 2)
        if not ok(x, y, 1.8) or not far(x, y, 5.0):
            continue
        if any((x - a) ** 2 + (y - b) ** 2 < 0.8 ** 2 for a, b in placed):
            continue
        placed.append((x, y))
        vn = variants[rng.integers(len(variants))]
        body.append(f'<body name="rk_x{added}" pos="{x:.2f} {y:.2f} {t.height(x, y):.3f}" '
                    f'euler="0 0 {rng.uniform(0, 360):.1f}">'
                    f'<geom type="mesh" mesh="{vn}" contype="0" conaffinity="0" group="1"/>'
                    f'</body>')
        added += 1

    # ---- 草簇：grass_medium_01 是扁平的扫描草皮，铺多了会变成一根根"灰刺"，
    #      所以只少量放在废墟附近，大面积的绿靠地面贴图
    if gmesh:
        added = 0
        for _ in range(120):
            if added >= 0:
                break
            x, y = cx + rng.normal(0, 12), cy + rng.normal(0, 12)
            if abs(x) > half or abs(y) > half or not ok(x, y, 1.9):
                continue
            body.append(f'<body name="gr_x{added}" pos="{x:.2f} {y:.2f} {t.height(x, y):.3f}" '
                        f'euler="0 0 {rng.uniform(0, 360):.1f}">'
                        f'<geom type="mesh" mesh="{gmesh}" contype="0" conaffinity="0" group="1"/>'
                        f'</body>')
            added += 1
        print(f"grass clumps: {added}")

    # ---- 房子专用相机
    gz_h = t.height(hx, hy)
    eye = np.array([hx - 15.0, hy - 13.0, gz_h + 8.0])
    tgt = np.array([hx, hy, gz_h + 1.6])
    d = tgt - eye
    d /= np.linalg.norm(d)
    right = np.cross(d, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, d)
    ax = " ".join(f"{v:.5f}" for v in [*right, *up])
    body.append(f'<camera name="house" pos="{eye[0]:.2f} {eye[1]:.2f} {eye[2]:.2f}" xyaxes="{ax}"/>')

    xml = xml.replace("</asset>", "".join(new_assets) + "</asset>", 1)
    xml = xml.replace("</worldbody>", "".join(body) + "</worldbody>", 1)
    open(args.dst, "w", encoding="utf-8").write(xml)
    print(f"wrote {args.dst}: +{len(new_assets)} mesh assets, +{len(body)} bodies, {len(xml)} bytes")


if __name__ == "__main__":
    main()
