r"""给人形 G1 造一个带台阶的院子：以官方 12dof 场景为底，只往里加地形块。

    python make_g1_yard.py --tier stairs
    python make_g1_yard.py --tier flat|full

为什么以官方场景为底：`<default>`（joint damping/armature/frictionloss）和地面材质
必须和策略训练时一致，否则它会"站住不走"或"走两步就摔"（两种都实测过）。
所以这里只把 terrain_tool 生成的地形 geom 追加进去，其余原样保留。

产物：assets/g1_yard_<tier>.xml（nq=19 / nu=12）
"""
import argparse
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
BASE = os.path.join(ASSETS, "props", "robots", "g1", "g1_12dof_scene.xml")
RAW = os.path.join(ASSETS, "_g1_yard_raw.xml")


def build_terrain(tier):
    import terrain_generator as tg
    tg.INPUT_SCENE_PATH = os.path.join(HERE, "unitree_terrain", "scene.xml")
    tg.OUTPUT_DIR = os.path.join(ASSETS, "terrain")
    tg.OUTPUT_SCENE_PATH = RAW
    g = tg.TerrainGenerator()
    stats = []
    if tier in ("stairs", "full"):
        g.AddStairs(init_pos=[1.2, 0.0, 0.0], yaw=0.0, width=0.30, height=0.15,
                    length=2.5, stair_nums=6)
        stats.append("台阶 6×0.15 m（x=1.5，朝 +y 铺开）")
        g.AddSuspendStairs(init_pos=[1.2, 0.0, 0.0], yaw=0.0, width=0.30, height=0.15,
                           length=2.5, gap=0.1, stair_nums=6)
        stats.append("悬空台阶 gap 0.1 m")
    if tier == "full":
        g.AddRoughGround(init_pos=[4.0, 0.0, 0.0], euler=[0, 0, 0], nums=[6, 6])
        stats.append("碎石阵 6×6")
        g.AddPerlinHeighField(position=[-5.0, 0.0, 0.0], size=[6.0, 6.0],
                              height_scale=0.2, negative_height=0.15)
        stats.append("Perlin ±0.2 m")
    if not stats:
        stats.append("纯平地（不加地形块）")
    g.Save()
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=("flat", "stairs", "full"), default="stairs")
    a = ap.parse_args()

    print("[1/2] terrain_tool 生成地形块")
    for s in build_terrain(a.tier):
        print("   " + s)

    print("[2/2] 把地形 geom 追加进官方 G1 场景（保留 default / 地面材质）")
    base = open(BASE, encoding="utf-8").read()
    # 产物放在 assets/ 下，meshdir 要改成相对 assets/ 的路径
    base = base.replace('meshdir="meshes/"', 'meshdir="props/robots/g1/meshes/"')
    raw = open(RAW, encoding="utf-8").read()
    world = re.search(r"<worldbody>(.*?)</worldbody>", raw, re.S).group(1)
    # 只要地形 geom，不要模板的 floor / light / 相机 / include
    geoms = re.findall(r'<geom[^>]*type="(?:box|cylinder|hfield|sphere)"[^>]*/>', world)
    base = re.sub(r"(</worldbody>)", "\n    " + "\n    ".join(geoms) + "\n  </worldbody>",
                  base, count=1)
    out = os.path.join(ASSETS, f"g1_yard_{a.tier}.xml")
    open(out, "w", encoding="utf-8").write(base)
    os.remove(RAW)

    import mujoco
    m = mujoco.MjModel.from_xml_path(out)
    print(f"   +{len(geoms)} 个地形 geom → {os.path.basename(out)} "
          f"nq={m.nq} nu={m.nu} ngeom={m.ngeom}")
    assert (m.nq, m.nu) == (19, 12)


if __name__ == "__main__":
    main()
