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

from roadgen import write_road_obj
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


def model_house(plot, gz, mesh_name, mat_name):
    """真实模型插槽：整栋按 plot 的尺寸归一化（按最大边长缩放）。"""
    return (f'<body name="{plot["id"]}" pos="{plot["x"]:.2f} {plot["y"]:.2f} {gz:.3f}" '
            f'euler="0 0 {plot["yaw"]}">'
            f'<geom type="mesh" mesh="{mesh_name}" material="{mat_name}" '
            f'contype="0" conaffinity="0" group="1"/></body>')


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
        gz = min(t.height(cx_, cy_) for cx_, cy_ in corners)  # 取最低角，避免悬空
        rel_model = (p.get("model") or "").strip()
        if rel_model and os.path.exists(os.path.join(ASSETS, rel_model)):
            if rel_model not in used_models:
                name = f"bld{len(used_models)}"
                stem = os.path.splitext(os.path.basename(rel_model))[0]
                png = os.path.join(os.path.dirname(rel_model), f"{stem}_diffuse.png")
                msc = p.get("model_scale") or 1.0
                sc_attr = f' scale="{msc} {msc} {msc}"' if msc != 1.0 else ""
                extra_assets.append(f'<mesh name="{name}" file="{rel_model}"{sc_attr}/>')
                mat = f"{name}_mat"
                if os.path.exists(os.path.join(ASSETS, png)):
                    extra_assets.append(f'<texture name="{name}_tex" type="2d" file="{png}"/>')
                    extra_assets.append(f'<material name="{mat}" texture="{name}_tex"/>')
                else:
                    extra_assets.append(f'<material name="{mat}" rgba="0.6 0.58 0.55 1"/>')
                used_models[rel_model] = (name, mat)
            body.append(model_house(p, gz, *used_models[rel_model]))
        else:
            if rel_model:
                print(f"  ! {p['id']}: model not found ({rel_model}), using placeholder")
            body.append(build_house(p, gz, rng))
        # 任务分配用的标记点
        body.append(f'<site name="site_{p["id"]}" pos="{p["x"]:.2f} {p["y"]:.2f} {gz + p["size"][2] / 2:.2f}" '
                    f'size="0.35" rgba="0.95 0.85 0.2 1"/>')
        print(f"  {p['id']:<3s} ({p['x']:>6.1f},{p['y']:>6.1f})  z={gz:6.2f}  damage={p['damage']}")

    # ---- 道路：生成一整条贴合地形的 ribbon 网格（比一堆方板像路）
    write_road_obj(road["points"], road["width"], t.height,
                   os.path.join(ASSETS, "generated", "road.obj"))
    extra_assets.append('<mesh name="roadmesh" file="generated/road.obj"/>')
    extra_assets.append('<material name="dirtroad" texture="dirt_tex" texuniform="false" '
                        'rgba="0.52 0.43 0.32 1" specular="0.02" shininess="0.1"/>')
    body.append('<geom name="road" type="mesh" mesh="roadmesh" material="dirtroad" '
                'contype="0" conaffinity="0" group="1"/>')

    # ---- 集结点
    ap_pt = cfg["assembly_point"]
    gz_ap = t.height(ap_pt["x"], ap_pt["y"])
    body.append(f'<site name="site_{ap_pt["name"]}" pos="{ap_pt["x"]:.2f} {ap_pt["y"]:.2f} {gz_ap + 0.1:.2f}" '
                f'size="1.2" rgba="0.2 0.7 0.95 1"/>')
    print(f"assembly {ap_pt['name']} ({ap_pt['x']}, {ap_pt['y']})")

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

    xml = xml.replace("</asset>", "".join(extra_assets) + "</asset>", 1)
    xml = xml.replace("</worldbody>", "".join(body) + "</worldbody>", 1)
    open(args.out, "w", encoding="utf-8").write(xml)
    print(f"wrote {args.out}: +{len(body)} bodies, {len(xml)} bytes")


if __name__ == "__main__":
    main()
