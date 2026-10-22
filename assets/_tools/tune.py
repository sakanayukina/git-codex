r"""不用 Blender 的真实感微调：把一个 XML 复制成加强版，只改材质与光照。

    python tune.py --in ..\demo_rescue_scene.xml --out ..\demo_v2.xml
    python tune.py --out ..\demo_v3.xml --ground-tex leafy_grass

做这些事（都可在 MuJoCo 内部完成）：
1. 废墟块 / 楼板从纯白 rgba 换成混凝土贴图
2. 地面贴图可换、重复率提高、色调压回中性
3. 主光降强度、去掉过曝，补光加一点天空色
4. 确保阴影贴图 8192、头灯环境光降一点
"""
import argparse
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ASSETS, "demo_rescue_scene.xml"))
    ap.add_argument("--out", dest="dst", default=os.path.join(ASSETS, "demo_v2.xml"))
    ap.add_argument("--ground-tex", default="", help="tex/ 下的贴图名，如 leafy_grass")
    args = ap.parse_args()

    xml = open(args.src, encoding="utf-8").read()
    orig = xml

    # 1) 混凝土材质注入
    if "concrete_tex" not in xml:
        ins = ('<texture name="concrete_tex" type="2d" file="tex/concrete_floor_diffuse.png"/>'
               '<material name="concrete" texture="concrete_tex" texrepeat="3 3" '
               'texuniform="true" rgba="0.78 0.77 0.74 1" specular="0.05" shininess="0.15"/>')
        xml = xml.replace("<hfield name=", ins + "\n    <hfield name=", 1)

    # 2) 白色方盒 -> 混凝土
    xml = xml.replace('rgba="0.62 0.60 0.57 1"', 'material="concrete"')
    xml = xml.replace('rgba="0.70 0.68 0.64 1"', 'material="concrete"')

    # 3) 换成别的草/土贴图
    if args.ground_tex:
        xml = re.sub(r'file="tex/[a-z0-9_]+_diffuse\.png"',
                     f'file="tex/{args.ground_tex}_diffuse.png"', xml, count=1)

    # 4) 地面色调与重复率
    xml = re.sub(r'rgba="0\.92 0\.92 0\.88 1" texrepeat="24 24"',
                 'rgba="0.58 0.74 0.44 1" texrepeat="40 40"', xml)

    # 5) 光照：主光降温降强，补光/轮廓光提一点
    xml = xml.replace('diffuse="1.0 0.87 0.70"', 'diffuse="0.88 0.86 0.80"')
    xml = xml.replace('diffuse="0.22 0.27 0.36"', 'diffuse="0.26 0.30 0.40"')
    xml = xml.replace('diffuse="0.30 0.34 0.42"', 'diffuse="0.34 0.38 0.46"')

    # 6) 阴影贴图与头灯
    if "shadowsize" not in xml:
        xml = xml.replace("<visual>", '<visual><quality shadowsize="8192"/>', 1)
    xml = xml.replace('ambient="0.42 0.42 0.42"', 'ambient="0.30 0.31 0.34"')

    open(args.dst, "w", encoding="utf-8").write(xml)
    changed = sum(1 for a, b in zip(orig.splitlines(), xml.splitlines()) if a != b)
    print(f"wrote {args.dst}: {changed} lines changed, {len(orig)} -> {len(xml)} bytes")
    print(f"  ground tex: {args.ground_tex or '(unchanged)'}")


if __name__ == "__main__":
    main()
