r"""按 buildings.json 生成村落布局：多栋房 + 土路 + 集结点 + 树林分区 + 俯视相机。

    python village.py --base ..\demo_v5.xml --out ..\demo_v6.xml

设计要点：
- 房子是**插槽**：plot 的 model 字段填了路径就用真实模型（OBJ+贴图），没填就用程序化占位房。
  等你找到真实废墟模型，丢进 assets/props/buildings/<name>/，改 buildings.json 一行即可换。
- 每栋房子生成一个 <site> 标记（site_H1..），任务分配算法直接读坐标，不用硬编码。
- 村内清空树，西北坡加密，道路两侧留 5 m 走廊。
- 附带俯视相机 top，可直接渲论文用的布局图。
"""
import argparse
import json
import math
import os
import re

import numpy as np

from roadgen import write_roads_obj, write_road_obj
from scatter import Terrain, conifer_body, find_terrain

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


# ---------------------------------------------------------------- 几何辅助
def box_body(name, x, y, z, sx, sy, sz, yaw, mat=""):
    return (f'<body name="{name}" pos="{x:.2f} {y:.2f} {z:.3f}" euler="0 0 {yaw:.1f}">'
            f'<geom type="box" size="{sx:.2f} {sy:.2f} {sz:.2f}"{mat}/></body>')


def road_mesh(points, width, z_of, mat=' material="dirt"', step=1.5):
    """把折线切成 ~2.5 m 的小段，逐段贴合地形（长段会钻进坡里）。"""
    out = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(length / step))
        for i in range(n):
            t0, t1 = i / n, (i + 1) / n
            ax, ay = x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0
            bx, by = x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1
            mx, my = (ax + bx) / 2, (ay + by) / 2
            seg = math.hypot(bx - ax, by - ay)
            yaw = math.degrees(math.atan2(by - ay, bx - ax))
            za, zb = z_of(ax, ay), z_of(bx, by)
            tilt = math.degrees(math.atan2(zb - za, max(seg, 1e-6)))
            out.append(f'<geom type="box" size="{seg / 2 + 1.0:.2f} {width / 2:.2f} 0.06" '
                       f'pos="{mx:.2f} {my:.2f} {(za + zb) / 2 + 0.05:.2f}" '
                       f'euler="0 {tilt:.1f} {yaw:.1f}"{mat}/>')
    return "".join(out)


def dist_to_polyline(x, y, pts):
    best = 1e9
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / L2))
        px, py = x0 + t * dx, y0 + t * dy
        best = min(best, math.hypot(x - px, y - py))
    return best


# ---------------------------------------------------------------- 房子
def build_house(plot, gz, rng):
    """按 damage 等级拼一栋房子；结构对、细节是占位级别。"""
    pid, W, D, H = plot["id"], plot["size"][0], plot["size"][1], plot["size"][2]
    th = 0.22
    out = [f'<body name="{pid}" pos="{plot["x"]:.2f} {plot["y"]:.2f} {gz:.3f}" '
           f'euler="0 0 {plot["yaw"]}">']
    out.append(f'<geom type="box" size="{W / 2 + 0.3:.2f} {D / 2 + 0.3:.2f} 0.15" '
               f'pos="0 0 0.12" material="concrete"/>')
    # 坡地上的房子会在下坡侧悬空，用一段"地基"往下埋 0.9 m 挡住缝
    out.append(f'<geom type="box" size="{W / 2 + 0.35:.2f} {D / 2 + 0.35:.2f} 0.5" '
               f'pos="0 0 -0.35" material="concrete"/>')

    def wall(u0, u1, v, h0, h1, material="brick"):
        out.append(f'<geom type="box" size="{(u1 - u0) / 2:.2f} {th / 2:.2f} {(h1 - h0) / 2:.2f}" '
                   f'pos="{(u0 + u1) / 2:.2f} {v:.2f} {(h0 + h1) / 2 + 0.15:.2f}" material="{material}"/>')

    dmg = plot["damage"]
    if dmg == "intact":
        wall(-W / 2, W / 2, D / 2, 0, H)
        wall(-W / 2, W / 2, -D / 2, 0, H)
        wall(-W / 2, -W / 2 + 0.01, 0, 0, 0) if False else None
        for v in (-D / 2, D / 2):
            pass
        out.append(f'<geom type="box" size="{th / 2:.2f} {D / 2:.2f} {H / 2:.2f}" '
                   f'pos="{-W / 2:.2f} 0 {H / 2 + 0.15:.2f}" material="brick"/>')
        out.append(f'<geom type="box" size="{th / 2:.2f} {D / 2:.2f} {H / 2:.2f}" '
                   f'pos="{W / 2:.2f} 0 {H / 2 + 0.15:.2f}" material="brick"/>')
        out.append(f'<geom type="box" size="{W / 2 + 0.4:.2f} {D / 2 + 0.4:.2f} 0.12" '
                   f'pos="0 0 {H + 0.3:.2f}" euler="0 6 0" material="concrete"/>')
    else:
        # 南北墙留窗洞/门洞
        wall(-W / 2, W / 2, D / 2, 0.0, 1.05)
        wall(-W / 2, W / 2, D / 2, 2.05, H)
        wall(-W / 2, -W / 2 + 1.0, D / 2, 1.05, 2.05)
        wall(W / 2 - 1.0, W / 2, D / 2, 1.05, 2.05)
        wall(-0.9, 0.9, D / 2, 1.05, 2.05)
        wall(-W / 2, -1.1, -D / 2, 0.0, H)
        wall(1.1, W / 2, -D / 2, 0.0, H)
        wall(-1.1, 1.1, -D / 2, 2.1, H)
        if dmg == "half":
            out.append(f'<geom type="box" size="{th / 2:.2f} {D / 4:.2f} {H / 2:.2f}" '
                       f'pos="{W / 2:.2f} {-D / 4:.2f} {H / 2 + 0.15:.2f}" material="brick"/>')
            out.append(f'<geom type="box" size="{th / 2:.2f} {D / 5:.2f} 0.75" '
                       f'pos="{W / 2:.2f} {D / 3:.2f} 0.9" euler="0 -9 0" material="brick"/>')
            out.append(f'<geom type="box" size="{W / 2.8:.2f} {D / 2.8:.2f} 0.11" '
                       f'pos="{-0.5:.2f} {0.4:.2f} {2.4:.2f}" euler="24 -5 12" material="concrete"/>')
        else:  # collapse：东墙全塌、西墙半截、楼板砸进屋内
            out.append(f'<geom type="box" size="{th / 2:.2f} {D / 3:.2f} 0.55" '
                       f'pos="{-W / 2:.2f} {-D / 3:.2f} 0.7" material="brick"/>')
            out.append(f'<geom type="box" size="{W / 2.2:.2f} {D / 2.4:.2f} 0.12" '
                       f'pos="{0.2:.2f} {0.3:.2f} {1.2:.2f}" euler="18 6 -26" material="concrete"/>')
            for i in range(30):
                s = rng.uniform(0.08, 0.26)
                out.append(f'<geom type="box" size="{s:.3f} {s * 1.3:.3f} {s * 0.7:.3f}" '
                           f'pos="{rng.uniform(-W / 2, W / 2):.2f} {rng.uniform(-D / 2, D / 2):.2f} '
                           f'{rng.uniform(0.15, 1.0):.2f}" '
                           f'euler="{rng.uniform(0, 360):.0f} {rng.uniform(0, 360):.0f} {rng.uniform(0, 360):.0f}" '
                           f'rgba="0.46 0.44 0.41 1"/>')
    out.append("</body>")
    return "".join(out)


def model_house(plot, gz, parts):
    """真实模型插槽：parts = [(mesh_name, material), ...]，一个 body 挂多个 geom。

    大进深模型放在坡地上必然一侧陷进土里、一侧悬空（H2 是 16.7 m 长的木屋）。
    所以在下面垫一块混凝土基座，把缝挡住。
    """
    g = "".join(f'<geom type="mesh" mesh="{nm}" material="{mat}" '
                f'contype="0" conaffinity="0" group="1"/>' for nm, mat in parts)
    w, d = plot["size"][0] * 0.94, plot["size"][1] * 0.94
    plinth = (f'<geom type="box" size="{w / 2:.2f} {d / 2:.2f} 0.7" pos="0 0 -0.55" '
              f'material="concrete"/>')
    return (f'<body name="{plot["id"]}" pos="{plot["x"]:.2f} {plot["y"]:.2f} {gz:.3f}" '
            f'euler="0 0 {plot["yaw"]}">{plinth}{g}</body>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.join(ASSETS, "demo_v5.xml"))
    ap.add_argument("--out", default=os.path.join(ASSETS, "demo_v6.xml"))
    ap.add_argument("--config", default=os.path.join(ASSETS, "buildings.json"))
    ap.add_argument("--seed", type=int, default=23)
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    xml = open(args.base, encoding="utf-8").read()
    rng = np.random.default_rng(args.seed)

    # 去掉旧的单栋房子
    xml = re.sub(r'<body name="house"[^>]*>.*?</body>', "", xml, flags=re.S)

    png_rel, extent, relief, base_z = find_terrain(xml)
    t = Terrain(os.path.join(ASSETS, png_rel), extent, relief, base_z)

    road = cfg["road"]
    plots = cfg["plots"]

    # ---- 村内清树：房子周围 11 m、道路两侧 5 m
    def inside_keepout(px, py):
        for p in plots:
            if math.hypot(px - p["x"], py - p["y"]) < 11.0 + max(p["size"][:2]) / 2:
                return True
        return dist_to_polyline(px, py, road["points"]) < 5.0

    removed = 0
    for m in list(re.finditer(r'<body name="tree_x\d+" pos="([-\d.]+) ([-\d.]+) [-\d.]+".*?</body>', xml, flags=re.S)):
        px, py = float(m.group(1)), float(m.group(2))
        if inside_keepout(px, py):
            xml = xml.replace(m.group(0), "")
            removed += 1
    print(f"trees removed inside village/road: {removed}")

    # ---- 材质（土路 / 真实模型贴图占位）
    extra_assets = ['<texture name="dirt_tex" type="2d" file="tex/forest_floor_diffuse.png"/>',
                    '<material name="dirt" texture="dirt_tex" texrepeat="6 2" texuniform="true" '
                    'rgba="0.70 0.66 0.58 1" specular="0.02" shininess="0.1"/>']

    body = []

    # ---- 房子（有 model 就换真实模型）
    used_models = {}
    for p in plots:
        corners = [(p["x"] + dx, p["y"] + dy)
                   for dx in (-p["size"][0] / 2, p["size"][0] / 2)
                   for dy in (-p["size"][1] / 2, p["size"][1] / 2)]
        gz = max(t.height(cx_, cy_) for cx_, cy_ in corners)  # 取最高角：靠基座填坡，避免埋进土里
        rel_model = (p.get("model") or "").strip()
        abs_model = os.path.join(ASSETS, rel_model) if rel_model else ""
        if rel_model and os.path.exists(abs_model):
            if rel_model not in used_models:
                parts = []
                msc = p.get("model_scale") or 1.0
                sc_attr = f' scale="{msc} {msc} {msc}"' if msc != 1.0 else ""
                if os.path.isdir(abs_model):
                    # 导出器按材质拆成了多个 obj：整栋 = 一个 body 挂多个 geom
                    for k, f in enumerate(sorted(x for x in os.listdir(abs_model) if x.endswith(".obj"))):
                        nm = f"bld{len(used_models)}_{k}"
                        extra_assets.append(
                            f'<mesh name="{nm}" file="{rel_model}/{f}" inertia="shell"{sc_attr}/>')
                        mat = f"{nm}_mat"
                        # 贴图名可能是 <材质>_diffuse.png，也可能是共享的 atlas_N.png，
                        # convert_multi 会在目录里写 manifest.json 说明对应关系
                        png = None
                        man = os.path.join(abs_model, "manifest.json")
                        if os.path.exists(man):
                            for part in json.load(open(man, encoding="utf-8")).get("parts", []):
                                if part.get("obj") == f and part.get("png"):
                                    png = f"{rel_model}/{part['png']}"
                                    break
                        if png is None:
                            cand = f"{rel_model}/{f[:-4]}_diffuse.png"
                            png = cand if os.path.exists(os.path.join(ASSETS, cand)) else None
                        if png and os.path.exists(os.path.join(ASSETS, png)):
                            extra_assets.append(f'<texture name="{nm}_tex" type="2d" file="{png}"/>')
                            extra_assets.append(
                                f'<material name="{mat}" texture="{nm}_tex" specular="0.05" shininess="0.1"/>')
                        else:
                            extra_assets.append(f'<material name="{mat}" rgba="0.62 0.60 0.56 1"/>')
                        parts.append((nm, mat))
                else:
                    nm = f"bld{len(used_models)}"
                    stem = os.path.splitext(os.path.basename(rel_model))[0]
                    png = os.path.join(os.path.dirname(rel_model), f"{stem}_diffuse.png")
                    extra_assets.append(f'<mesh name="{nm}" file="{rel_model}"{sc_attr}/>')
                    mat = f"{nm}_mat"
                    if os.path.exists(os.path.join(ASSETS, png)):
                        extra_assets.append(f'<texture name="{nm}_tex" type="2d" file="{png}"/>')
                        extra_assets.append(f'<material name="{mat}" texture="{nm}_tex"/>')
                    else:
                        extra_assets.append(f'<material name="{mat}" rgba="0.6 0.58 0.55 1"/>')
                    parts.append((nm, mat))
                used_models[rel_model] = parts
            body.append(model_house(p, gz, used_models[rel_model]))
        else:
            if rel_model:
                print(f"  ! {p['id']}: model not found ({rel_model}), using placeholder")
            body.append(build_house(p, gz, rng))
        # 任务分配用的标记点
        body.append(f'<site name="site_{p["id"]}" pos="{p["x"]:.2f} {p["y"]:.2f} {gz + p["size"][2] / 2:.2f}" '
                    f'size="0.35" rgba="0.95 0.85 0.2 1" group="3"/>')
        print(f"  {p['id']:<3s} ({p['x']:>6.1f},{p['y']:>6.1f})  z={gz:6.2f}  damage={p['damage']}")

    # ---- 道路：主路 + 每户门前支路，合成一个 ribbon 网格
    main_pts = road["points"]
    polylines, widths = [main_pts], [road["width"]]

    def closest_on_polyline(x, y, pts):
        best, bd = None, 1e18
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / L2))
            px, py = x0 + t * dx, y0 + t * dy
            d = (x - px) ** 2 + (y - py) ** 2
            if d < bd:
                best, bd = (px, py), d
        return best

    junctions = []
    for p in plots:
        a = math.radians(p["yaw"])
        # 门在局部 (0, -D/2)，转到世界坐标
        dx, dy = math.sin(a) * p["size"][1] / 2, -math.cos(a) * p["size"][1] / 2
        door = (p["x"] + dx, p["y"] + dy)
        target = closest_on_polyline(door[0], door[1], main_pts)
        if target is None or math.hypot(door[0] - target[0], door[1] - target[1]) < 1.0:
            continue
        mid = ((door[0] + target[0]) / 2, (door[1] + target[1]) / 2)
        polylines.append([target, mid, door])
        widths.append(3.0)
        junctions.append((target, 3.0))

    # 注意：这里**不再**生成贴地道路网格——路已经烘进地面贴图了。
    # 留着旧的 mesh 会盖在烘焙贴图上面，把路盖成一条发白的带子（踩过）。
    print(f"road: {len(polylines)} 条（主路 + {len(polylines) - 1} 条入户支路，全部烘进地面贴图）")

    # ---- 地面：把主路 + 入户支路一起烘进地形贴图（贴地网格会抖动+边缘锯齿）
    baked = os.path.join(ASSETS, "tex", "ground_baked.png")
    try:
        from bake_ground import bake
        bake(extent, list(zip(polylines, widths)),
             os.path.join(ASSETS, "tex", "leafy_grass_diffuse.png"), baked, 2048,
             junctions=junctions)
        xml = xml.replace('file="tex/leafy_grass_diffuse.png"', 'file="tex/ground_baked.png"')
        xml = re.sub(r'(name="gmat"[^>]*?rgba=")[^"]*(")', r"\g<1>1 1 1 1\g<2>", xml)
        # hfield 的 texrepeat 按"米"计，不是按整块地形归一化：
        # 要 1:1 覆盖 extent 米，就填 1/extent（200 m -> 0.005），填 1 1 会变成每米铺一次。
        rep = 1.0 / extent
        xml = re.sub(r'(name="gmat"[^>]*?texrepeat=")[^"]*(")',
                     rf"\g<1>{rep:.6f} {rep:.6f}\g<2>", xml)
        print(f"ground: 烘好的地面贴图已启用（{os.path.getsize(baked)/1e6:.1f} MB, 2048x2048）")
    except Exception as e:      # 烘焙失败也不阻塞场景生成
        print(f"! ground bake skipped: {e}")

    # ---- 集结点
    ap_pt = cfg["assembly_point"]
    gz_ap = t.height(ap_pt["x"], ap_pt["y"])
    body.append(f'<site name="site_{ap_pt["name"]}" pos="{ap_pt["x"]:.2f} {ap_pt["y"]:.2f} {gz_ap + 0.1:.2f}" '
                f'size="1.2" rgba="0.2 0.7 0.95 1" group="3"/>')
    print(f"assembly {ap_pt['name']} ({ap_pt['x']}, {ap_pt['y']})")

    # ---- 碰撞外壳：真实模型的房子只有视觉几何（contype=0），机器人会穿墙。
    #      这里补一圈不可见的墙（group=3 默认不渲染），留一个门洞。
    for p in plots:
        if not (p.get("model") or "").strip():
            continue
        if p.get("collision", "walls") == "none":
            continue
        W, D, H = p["size"][0], p["size"][1], p["size"][2]
        # 可选覆盖：collision_box = [宽, 进深, 高, 门洞宽]
        # 例如 H6 只有中间楼体要挡（外面一圈是瓦砾），H7 是一堵墙（门洞 0）
        box = p.get("collision_box")
        if box:
            W, D, H = box[0], box[1], box[2]
            door = box[3] if len(box) > 3 else 1.3
        else:
            door = 1.3
        corners = [(p["x"] + dx, p["y"] + dy) for dx in (-W / 2, W / 2) for dy in (-D / 2, D / 2)]
        gz = min(t.height(cx_, cy_) for cx_, cy_ in corners)
        th = 0.18
        seg = max(0.05, (W / 2 - door / 2) / 2)
        shell = [f'<body name="{p["id"]}_collision" pos="{p["x"]:.2f} {p["y"]:.2f} {gz:.3f}" '
                 f'euler="0 0 {p["yaw"]}">']
        # 前墙（留门洞；门洞 0 就是整面实墙）
        if door > 0:
            for s in (-1, 1):
                shell.append(f'<geom type="box" size="{seg:.2f} {th:.2f} {H / 2:.2f}" '
                             f'pos="{s * (door / 2 + seg):.2f} {-D / 2:.2f} {H / 2:.2f}" group="3"/>')
            shell.append(f'<geom type="box" size="{door / 2:.2f} {th:.2f} 0.55" '
                         f'pos="0 {-D / 2:.2f} {H - 0.55:.2f}" group="3"/>')   # 门楣
        else:
            shell.append(f'<geom type="box" size="{W / 2:.2f} {th:.2f} {H / 2:.2f}" '
                         f'pos="0 {-D / 2:.2f} {H / 2:.2f}" group="3"/>')
        # 后墙 + 两侧墙
        shell.append(f'<geom type="box" size="{W / 2:.2f} {th:.2f} {H / 2:.2f}" '
                     f'pos="0 {D / 2:.2f} {H / 2:.2f}" group="3"/>')
        for s in (-1, 1):
            shell.append(f'<geom type="box" size="{th:.2f} {D / 2:.2f} {H / 2:.2f}" '
                         f'pos="{s * W / 2:.2f} 0 {H / 2:.2f}" group="3"/>')
        shell.append("</body>")
        body.append("".join(shell))
        print(f"  collision shell for {p['id']}")

    # ---- 西北坡加密林（村庄外围成片），南侧少
    added = 0
    for _ in range(4000):
        if added >= 70:
            break
        x, y = rng.uniform(-95, -18), rng.uniform(6, 95)
        if inside_keepout(x, y) or t.slope(x, y) > 1.6:
            continue
        h = rng.uniform(7.0, 17.0)
        body.append(conifer_body(f"tree_v{added}", x, y, t.height(x, y), h, rng,
                                 np.array([0.075, 0.20, 0.085])))
        added += 1
    print(f"northwest forest added: {added}")

    # ---- 真实草簇（扫描件，铺在地面上；无碰撞、无 site）
    gdir = os.path.join(ASSETS, "props", "imported", "grass_chunks")
    gman = os.path.join(gdir, "manifest.json")
    if os.path.exists(gman):
        want = ("rostlinka_07c", "ground_close_04", "rostlinka12_2k")   # 丢掉 52k 面那块
        variants = []
        for p in json.load(open(gman, encoding="utf-8"))["parts"]:
            if p["material"] not in want:
                continue
            nm = f"gc{len(variants)}"
            extra_assets.append(
                f'<mesh name="{nm}" file="props/imported/grass_chunks/{p["obj"]}" inertia="shell"/>')
            mat = f"{nm}_mat"
            extra_assets.append(
                f'<texture name="{nm}_tex" type="2d" file="props/imported/grass_chunks/{p["png"]}"/>')
            extra_assets.append(f'<material name="{mat}" texture="{nm}_tex" '
                                f'specular="0.02" shininess="0.1"/>')
            variants.append((nm, mat))
        gc = 0
        half_g = extent / 2 - 6
        for _ in range(4000):
            if gc >= 45:
                break
            x, y = rng.uniform(-half_g, half_g, 2)
            if t.slope(x, y) > 1.9 or inside_keepout(x, y):
                continue
            nm, mat = variants[rng.integers(len(variants))]
            body.append(f'<body name="grass_{gc}" pos="{x:.2f} {y:.2f} {t.height(x, y):.3f}" '
                        f'euler="0 0 {rng.uniform(0, 360):.1f}">'
                        f'<geom type="mesh" mesh="{nm}" material="{mat}" '
                        f'contype="0" conaffinity="0" group="1"/></body>')
            gc += 1
        print(f"grass clumps (real scan): {gc}")

    # ---- 真实枫树（导入的 Sketchfab CC-BY 模型，按材质拆成 bark + leaf 两个 mesh）
    half = extent / 2 - 8
    placed = []
    maple_dir = os.path.join(ASSETS, "props", "imported", "maple")
    if os.path.isdir(maple_dir):
        parts = sorted(f for f in os.listdir(maple_dir)
                       if f.endswith(".obj") and "metallic" not in f)
        scales = (0.75, 1.0, 1.25)
        variants = {}
        for sc in scales:
            for part in parts:
                nm = f"mp{len(variants)}"
                png = part[:-4] + "_diffuse.png"
                extra_assets.append(
                    f'<mesh name="{nm}" file="props/imported/maple/{part}" '
                    f'scale="{sc} {sc} {sc}" inertia="shell"/>')
                mat = f"{nm}_mat"
                if os.path.exists(os.path.join(maple_dir, png)):
                    extra_assets.append(
                        f'<texture name="{nm}_tex" type="2d" file="props/imported/maple/{png}"/>')
                    extra_assets.append(f'<material name="{mat}" texture="{nm}_tex" specular="0.02" shininess="0.1"/>')
                else:
                    extra_assets.append(f'<material name="{mat}" rgba="0.30 0.45 0.22 1"/>')
                variants[(part, sc)] = (nm, mat)

        madded = 0
        for _ in range(600):
            if madded >= 30:
                break
            x, y = rng.uniform(-half, half, 2)
            if inside_keepout(x, y) or t.slope(x, y) > 1.7:
                continue
            if any((x - a) ** 2 + (y - b) ** 2 < 3.0 ** 2 for a, b in placed):
                continue
            placed.append((x, y))
            sc = scales[rng.integers(len(scales))]
            yaw = rng.uniform(0, 360)
            g = [f'<body name="maple_{madded}" pos="{x:.2f} {y:.2f} {t.height(x, y):.3f}" '
                 f'euler="0 0 {yaw:.1f}">']
            for part in parts:
                nm, mat = variants[(part, sc)]
                g.append(f'<geom type="mesh" mesh="{nm}" material="{mat}" '
                         f'contype="0" conaffinity="0" group="1"/>')
            g.append("</body>")
            body.append("".join(g))
            madded += 1
        print(f"maple trees added: {madded}（材质分组 {len(parts)}）")

    # ---- 相机：村口视角 + 俯视图
    def cam(name, eye, target):
        pos = np.array(eye, float)
        d = np.array(target, float) - pos
        d /= np.linalg.norm(d)
        r = np.cross(d, [0, 0, 1.0])
        r /= np.linalg.norm(r)
        u = np.cross(r, d)
        ax = " ".join(f"{v:.5f}" for v in [*r, *u])
        return f'<camera name="{name}" pos="{pos[0]:.2f} {pos[1]:.2f} {pos[2]:.2f}" xyaxes="{ax}"/>'

    gz_c = t.height(0, -30)
    body.append(cam("village", (-18, -62, gz_c + 28), (6, 6, gz_c + 2)))
    body.append('<camera name="top" pos="2 2 320" xyaxes="1 0 0 0 1 0"/>')

    # 每栋房一个正面相机（从村道方向看门窗），并修掉旧的 close（它会插进墙里）
    xml = re.sub(r'<camera name="close"[^>]*/>', "", xml)
    for p in plots:
        gz_p = t.height(p["x"], p["y"])
        eye = (p["x"] - 10.0, p["y"] - 13.0, gz_p + 5.5)
        body.append(cam(f"cam_{p['id']}", eye, (p["x"], p["y"], gz_p + 2.2)))
    h1 = next((p for p in plots if p["id"] == "H1"), plots[0])
    gz_h1 = t.height(h1["x"], h1["y"])
    body.append(cam("close", (h1["x"] - 11.0, h1["y"] - 14.0, gz_h1 + 5.0),
                    (h1["x"], h1["y"], gz_h1 + 2.0)))

    xml = xml.replace("</asset>", "".join(extra_assets) + "</asset>", 1)
    xml = xml.replace("</worldbody>", "".join(body) + "</worldbody>", 1)
    open(args.out, "w", encoding="utf-8").write(xml)
    print(f"wrote {args.out}: +{len(body)} bodies, {len(xml)} bytes")


if __name__ == "__main__":
    main()
