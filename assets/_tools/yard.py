r"""生成"救援小院"：宇树 terrain_tool 的可控地形 + 我们的房子 + 机器人。

    python yard.py                 # 生成 assets/yard_v1.xml
    python yard.py --check         # 只报告参数

必须用 **base python** 跑（mujoco 环境的 numpy 会让 terrain_generator 崩）。
产物：
    assets/yard_v1.xml                              主场景
    assets/props/robots/go2_urdf/go2_robot.xml      只含机器人的 include 片段（自动生成）
"""
import argparse
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
TERRAIN_TOOL = os.path.join(HERE, "unitree_terrain")
GO2_SCENE = os.path.join(ASSETS, "props", "robots", "go2_urdf", "go2_scene.xml")
GO2_ROBOT = os.path.join(ASSETS, "props", "robots", "go2_urdf", "go2_robot.xml")
DEMO = os.path.join(ASSETS, "demo_v27.xml")
YARD = os.path.join(ASSETS, "yard_v1.xml")
RAW = os.path.join(ASSETS, "_yard_raw.xml")

# 房子在院子里的位置（x, y, yaw）
HOUSE = (0.0, 12.0, 180.0)      # 房子实际 12.6 m 长，得往后挪，别压住地形模块


def make_robot_file():
    """从 go2_scene.xml 抽出"只有机器人"的片段，供 yard 用 <include> 引入。"""
    x = open(GO2_SCENE, encoding="utf-8").read()
    x = re.sub(r"\s*<option[^>]*/>", "", x)
    x = re.sub(r"\s*<visual>.*?</visual>", "", x, flags=re.S)
    x = re.sub(r'\s*<geom name="floor"[^>]*/>', "", x)
    x = re.sub(r'\s*<light [^>]*/>', "", x)
    x = re.sub(r'\s*<camera name="track"[^>]*/>', "", x)
    open(GO2_ROBOT, "w", encoding="utf-8").write(x)
    return len(x)


def build_terrain(tier="full"):
    """tier: flat（纯平地）/ stairs（加台阶）/ full（再加碎石与起伏）。"""
    import terrain_generator as tg

    tg.INPUT_SCENE_PATH = os.path.join(TERRAIN_TOOL, "scene.xml")
    tg.OUTPUT_DIR = os.path.join(ASSETS, "terrain")
    tg.OUTPUT_SCENE_PATH = RAW
    g = tg.TerrainGenerator()

    stats = []
    if tier in ("stairs", "full"):
        # 0.15 m 台阶 × 6
        g.AddStairs(init_pos=[-9.0, 2.0, 0.0], yaw=0.0, width=0.30, height=0.15,
                    length=2.0, stair_nums=6)
        stats.append("台阶 6×0.15 m")
        # 0.1 m 缝的悬空台阶
        g.AddSuspendStairs(init_pos=[-9.0, -4.0, 0.0], yaw=0.0, width=0.30, height=0.15,
                           length=2.0, gap=0.1, stair_nums=6)
        stats.append("悬空台阶 6 级 (gap 0.1 m)")
    if tier == "full":
        # 碎石阵：0.5 m 方块，8×8
        g.AddRoughGround(init_pos=[5.0, -6.0, 0.0], euler=[0, 0, 0], nums=[8, 8])
        stats.append("碎石阵 8×8 (0.5 m 块)")
        # 起伏 0.2 m 的 Perlin 地形 8×8 m
        g.AddPerlinHeighField(position=[5.0, 4.0, 0.0], size=[8.0, 8.0],
                              height_scale=0.2, negative_height=0.05)
        stats.append("Perlin 起伏 ±0.2 m (8×8 m)")
    if not stats:
        stats.append("纯平地（训练分布内）")
    g.Save()
    return stats


def inject_house(xml):
    """把 demo_v27 里 H1 的房子（15 个网格 + 碰撞壳）搬进院子。"""
    src = open(DEMO, encoding="utf-8").read()

    assets = re.findall(r'<mesh name="bld0_\d+"[^>]*/>', src)
    # demo_v27 里 H1 的 material 是纯色（没有贴图）——用共享图集补上
    atlas = os.path.join(ASSETS, "props", "imported", "ruin_uk", "ruin_uk_atlas_0.png")
    if os.path.exists(atlas):
        assets.append('<texture name="h1_atlas" type="2d" '
                      'file="props/imported/ruin_uk/ruin_uk_atlas_0.png"/>')
        assets.append('<material name="h1_mat" texture="h1_atlas" '
                      'specular="0.05" shininess="0.1"/>')
    else:
        assets.append('<material name="h1_mat" rgba="0.62 0.60 0.56 1"/>')

    body = re.search(r'<body name="H1"[^>]*>.*?</body>', src, re.S).group(0)
    coll = re.search(r'<body name="H1_collision"[^>]*>.*?</body>', src, re.S).group(0)
    body = re.sub(r'material="bld0_\d+_mat"', 'material="h1_mat"', body)

    hx, hy, hyaw = HOUSE
    # H1 在 demo 里是 (15,-14, z=5.599)，院子地面 z=0 → 直接换成院子坐标
    body = re.sub(r'(<body name="H1" pos=")[-\d.]+ [-\d.]+ [-\d.]+(" euler="0 0 )[-\d.]+(")',
                  lambda m: f"{m.group(1)}{hx:.2f} {hy:.2f} 0.00{m.group(2)}{hyaw}{m.group(3)}",
                  body, count=1)
    coll = re.sub(r'(<body name="H1_collision" pos=")[-\d.]+ [-\d.]+ [-\d.]+(" euler="0 0 )[-\d.]+(")',
                  lambda m: f"{m.group(1)}{hx:.2f} {hy:.2f} 0.00{m.group(2)}{hyaw}{m.group(3)}",
                  coll, count=1)

    xml = xml.replace("</asset>", "\n    " + "\n    ".join(assets) + "\n  </asset>", 1)
    xml = re.sub(r"(<worldbody>)", r"\1\n    " + body + "\n    " + coll, xml, count=1)
    return xml, len(assets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--tier", choices=("flat", "stairs", "full"), default="full",
                    help="地形难度：flat=纯平地 / stairs=台阶 / full=台阶+碎石+起伏")
    args = ap.parse_args()
    out_path = os.path.join(ASSETS, f"yard_{args.tier}.xml")

    print(f"[1/3] 生成机器人 include 片段（tier={args.tier}）")
    print(f"   go2_robot.xml {make_robot_file()/1024:.1f} KB")

    print("[2/3] 用宇树 terrain_tool 生成地形")
    for s in build_terrain(args.tier):
        print("   " + s)
    if args.check:
        return

    print("[3/3] 注入房子 + 机器人")
    xml = open(RAW, encoding="utf-8").read()
    xml = re.sub(r'\s*<include file="go2\.xml"[^>]*/>', "", xml)
    xml = re.sub(r"(<mujoco[^>]*>)",
                 r'\1\n  <include file="props/robots/go2_urdf/go2_robot.xml"/>', xml, count=1)
    xml = re.sub(r"(<mujoco[^>]*>)",
                 r'\1\n  <option timestep="0.002" integrator="implicitfast"/>', xml, count=1)
    # 打光：模板只有一盏 1.5 m 高的方向光，房子和 hfield 会黑成一片
    xml = re.sub(r"<light [^>]*/>",
                 '<light pos="0 0 6" dir="0 0 -1" directional="true" diffuse="0.55 0.55 0.55"/>'
                 '<light pos="8 -8 6" dir="-0.6 0.6 -1" diffuse="0.45 0.45 0.45"/>', xml, count=1)
    xml = re.sub(r'(<headlight [^>]*ambient=")[\d. ]+(")',
                 r"\g<1>0.45 0.45 0.45\g<2>", xml, count=1)
    xml, n_assets = inject_house(xml)
    # 离屏渲染缓冲（默认 640×480，出图会被卡）。注意 <visual> 里 <global> 只能有一个，
    # 所以是给已有的 global 补属性，而不是新插一个。
    if "offwidth" not in xml:
        if re.search(r"<global [^>]*/>", xml):
            xml = re.sub(r"<global ([^>]*?)/>", r'<global \1 offwidth="1280" offheight="800"/>',
                         xml, count=1)
        else:
            xml = re.sub(r"(<visual>)", r'\1\n    <global offwidth="1280" offheight="800"/>',
                         xml, count=1)
    # 出生点标记 + 相机
    xml = re.sub(r"(</worldbody>)",
                 '  <site name="site_start" pos="0 0 0.02" size="0.6" '
                 'rgba="0.2 0.9 0.4 1" group="3"/>\n'
                 '    <camera name="cam_yard" pos="13 -13 9" xyaxes="0.707 0.707 0 -0.35 0.35 0.87"/>\n'
                 '    <camera name="cam_start" pos="3 -3 1.4" xyaxes="0.707 0.707 0 -0.25 0.25 0.94"/>\n'
                 '  </worldbody>', xml, count=1)
    open(out_path, "w", encoding="utf-8").write(xml)
    os.remove(RAW)
    print(f"   H1 资产 {n_assets} 条（网格/贴图/材质）")
    print(f"wrote {os.path.relpath(out_path, ASSETS)} ({os.path.getsize(out_path)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
