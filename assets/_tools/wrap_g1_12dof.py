r"""给官方 g1_12dof.xml 套一层地面/光照/相机，产出可直接跑的可视场景。

    python wrap_g1_12dof.py

输入：props/robots/g1/g1_12dof_official.xml（官方原版，13 关节 / 12 个 motor 力矩）
输出：props/robots/g1/g1_12dof_scene.xml（nq=19 / nu=12 + 地面）
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
G1 = os.path.join(os.path.dirname(HERE), "props", "robots", "g1")
SRC = os.path.join(G1, "g1_12dof_official.xml")
DST = os.path.join(G1, "g1_12dof_scene.xml")

SCENE = """  <option timestep="0.002" integrator="implicitfast"/>
  <visual>
    <global offwidth="1280" offheight="800"/>
    <headlight diffuse="0.6 0.6 0.6" ambient="0.35 0.35 0.35" specular="0.1 0.1 0.1"/>
    <rgba haze="0.15 0.25 0.35 1"/>
  </visual>
"""

FLOOR = """    <light pos="0 0 3" dir="0 0 -1" directional="true" diffuse="0.7 0.7 0.7"/>
    <light pos="4 -4 2" dir="-1 1 -1" diffuse="0.35 0.35 0.35"/>
    <geom name="floor" type="plane" size="0 0 0.05" material="yard_ground"/>
    <camera name="track" pos="2.6 -2.6 1.4" xyaxes="0.707 0.707 0 -0.35 0.35 0.87"/>
"""

# 天空盒 + 地面棋盘：默认没有天空盒，出图背景是全黑，放进汇报文档很难看
ENV_ASSET = """    <texture type="skybox" builtin="gradient" rgb1="0.48 0.64 0.84"
             rgb2="0.86 0.90 0.94" width="512" height="3072"/>
    <texture type="2d" name="yard_grid" builtin="checker" mark="edge"
             rgb1="0.46 0.50 0.44" rgb2="0.40 0.44 0.38" markrgb="0.58 0.60 0.55"
             width="300" height="300"/>
    <material name="yard_ground" texture="yard_grid" texuniform="true" texrepeat="10 10"/>
"""


def main():
    s = open(SRC, encoding="utf-8").read()

    # 缺的 STL 用本地同名/近名件顶替（例如 torso_link_23dof_rev_1_0.STL → torso_link.STL），
    # 只影响外观，不影响运动学（XML 里已经写好惯性/关节锚点）
    msd = os.path.join(G1, "meshes")
    local = os.listdir(msd)
    remap = {}
    for f in sorted(set(re.findall(r'file="([^"]+\.STL)"', s))):
        if os.path.exists(os.path.join(msd, f)):
            continue
        stem = f.replace(".STL", "").split("_rev_")[0].split("_23dof")[0].split("_29dof")[0]
        cand = [x for x in local if x.endswith(".STL") and x.startswith(stem)]
        if cand:
            remap[f] = cand[0]
    for old, new in remap.items():
        s = s.replace(f'file="{old}"', f'file="{new}"')
        print(f"  替代 {old} → {new}")
    s = re.sub(r"<mujoco([^>]*)>", r"<mujoco\1>" + "\n" + SCENE, s, count=1)
    s = re.sub(r"<worldbody>", "<worldbody>\n" + FLOOR, s, count=1)
    # 天空盒 + 地面材质塞进 <asset>（官方模型只有 mesh，没有贴图）
    if "<asset>" in s:
        s = s.replace("<asset>", "<asset>\n" + ENV_ASSET, 1)
    else:
        s = s.replace("<worldbody>", "<asset>\n" + ENV_ASSET + "  </asset>\n  <worldbody>", 1)
    open(DST, "w", encoding="utf-8").write(s)

    import mujoco
    m = mujoco.MjModel.from_xml_path(DST)
    print(f"wrote {os.path.basename(DST)}  nq={m.nq} nu={m.nu} "
          f"mass={sum(m.body_mass):.1f} kg")
    assert (m.nq, m.nu) == (19, 12), "尺寸不对"
    print("  OK：19 / 12")


if __name__ == "__main__":
    main()
