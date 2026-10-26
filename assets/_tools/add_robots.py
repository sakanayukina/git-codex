r"""把 Go2（free）和 G1（fixed）两台机器人摆进村子集结点 P0。

    python add_robots.py                 # demo_v28.xml -> demo_v29.xml
    python add_robots.py --in a.xml --out b.xml

为什么单独一个后处理脚本：村子链是 Codex 的（8 步），机器人是 DSH 的，
放在最后一步注入，谁重跑链都不会互相覆盖。产出的 XML 里机器人是**独立 body**，
不改变原有任何房子/道具。
"""
import argparse
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
GO2 = os.path.join(ASSETS, "props", "robots", "go2_urdf", "go2_scene.xml")
G1 = os.path.join(ASSETS, "props", "robots", "g1", "g1_scene.xml")

# 相对集结点 P0 的偏移（米）与世界朝向（度）
PLACE = {
    "go2": dict(dx=1.5, dy=-0.5, yaw=90.0, stand=0.27, root="base"),
    "g1": dict(dx=-1.2, dy=0.6, yaw=110.0, stand=0.862, root="pelvis"),
}


def strip_scene(xml):
    """去掉机器人场景里属于"独立场景"的部分，只留 asset / worldbody / actuator / keyframe。"""
    xml = re.sub(r"\s*<option[^>]*/>", "", xml)
    xml = re.sub(r"\s*<visual>.*?</visual>", "", xml, flags=re.S)
    xml = re.sub(r"\s*<statistic[^>]*/>", "", xml)
    xml = re.sub(r'\s*<geom name="floor"[^>]*/>', "", xml)
    xml = re.sub(r"\s*<light [^>]*/>", "", xml)
    xml = re.sub(r'\s*<camera name="track"[^>]*/>', "", xml)
    return xml


def sections(xml):
    out = {}
    for tag in ("asset", "worldbody", "actuator", "keyframe"):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.S)
        if m:
            out[tag] = m.group(1)
    return out


def place_robot(xml, cfg, x, y, z, static=True):
    """把根 body 挪到 (x,y,z) 并设 yaw；有 keyframe 的话同步改 qpos 前 3 位。"""
    if static:
        # 村子是展示场景：焊接基座，机器人就停在放它的位置，不会因 0.26 m 量化台阶摔倒
        xml = re.sub(r"\s*<freejoint[^>]*/>", "", xml)
    root = cfg["root"]
    pat = rf'(<body name="{root}"[^>]*?pos=")([-\d.]+) ([-\d.]+) ([-\d.]+)(")'
    new, n = re.subn(pat, lambda m: f"{m.group(1)}{x:.2f} {y:.2f} {z:.3f}{m.group(5)}", xml, count=1)
    if n == 0:                                   # 没有 pos 属性
        new = re.sub(rf'(<body name="{root}")', rf'\1 pos="{x:.2f} {y:.2f} {z:.3f}"', xml, count=1)
    # yaw
    if 'euler="' in new.split(f'name="{root}"')[1].split(">")[0]:
        new = re.sub(rf'(<body name="{root}"[^>]*euler="0 0 )([-\d.]+)(")',
                     rf'\g<1>{cfg["yaw"]:g}\g<3>', new, count=1)
    else:
        new = re.sub(rf'(<body name="{root}"[^>]*?)>', rf'\1 euler="0 0 {cfg["yaw"]:g}">', new, count=1)
    # keyframe 的 qpos 前三位是自由关节位置
    new = re.sub(r'(qpos=")([-\d.]+) ([-\d.]+) ([-\d.]+) ',
                 lambda m: f"{m.group(1)}{x:.2f} {y:.2f} {z:.3f} ", new, count=1)
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ASSETS, "demo_v28.xml"))
    ap.add_argument("--out", dest="dst", default=os.path.join(ASSETS, "demo_v29.xml"))
    ap.add_argument("--cx", type=float, default=None, help="机器人锚点 x（默认用 site_P0）")
    ap.add_argument("--cy", type=float, default=None, help="机器人锚点 y")
    args = ap.parse_args()

    village = open(args.src, encoding="utf-8").read()
    m = re.search(r'<site name="site_P0" pos="([-\d.]+) ([-\d.]+) ([-\d.]+)"', village)
    if not m:
        raise SystemExit("找不到 site_P0")
    px, py, pz = (float(g) for g in m.groups())
    ground = pz - 0.02
    if args.cx is not None:
        px, py = args.cx, args.cy
    print(f"锚点 = ({px:.2f}, {py:.2f}), 地面 z ≈ {ground:.2f}")

    assets, bodies, act, keys = [], [], [], []
    for name, path, reldir in (("go2", GO2, "props/robots/go2_urdf"),
                               ("g1", G1, "props/robots/g1/meshes")):
        if not os.path.exists(path):
            print(f"  跳过 {name}：{os.path.relpath(path, ASSETS)} 不存在")
            continue
        cfg = PLACE[name]
        sec = sections(strip_scene(open(path, encoding="utf-8").read()))
        # 机器人 XML 里的 <mesh file="meshes/x.obj"> 是相对它自己目录的，
        # 内联进村子（assets/ 下）后必须补上目录前缀，否则找不到网格
        asset_xml = re.sub(r'file="(?![/A-Za-z]:)([^"]+)"',
                           lambda m: f'file="{reldir}/{m.group(1)}"',
                           sec.get("asset", ""))
        x, y = px + cfg["dx"], py + cfg["dy"]
        z = ground + cfg["stand"]
        body_xml = place_robot(sec["worldbody"], cfg, x, y, z)
        # 给 body 改个前缀，避免和别的 body 重名
        body_xml = body_xml.replace('"base"', f'"{name}_base"', 1) if name == "go2" else body_xml
        assets.append(asset_xml)
        bodies.append(body_xml)
        if "actuator" in sec:
            act.append(sec["actuator"])
        # 机器人自带的 keyframe 只有它自己那十几个 qpos，合并后（村子有 651 维）尺寸不符，
        # 丢掉，交给 set_standing.py 按整场 nq 重新生成
        print(f"  {name}: 放到 ({x:.2f}, {y:.2f}, {z:.2f})  yaw {cfg['yaw']:g}°")

    xml = village
    xml = xml.replace("</asset>", "".join(assets) + "\n  </asset>", 1)
    xml = re.sub(r"(</worldbody>)", "".join(bodies) + "\n    " + r"\1", xml, count=1)
    extra = ""
    if act:
        extra += "  <actuator>" + "".join(act) + "</actuator>\n"
    if keys:
        extra += "  <keyframe>" + "".join(keys) + "</keyframe>\n"
    if extra:
        xml = xml.replace("</mujoco>", extra + "</mujoco>", 1)
    # 一台相机对着机器人
    xml = re.sub(r"(</worldbody>)",
                 f'<camera name="cam_robots" pos="{px + 6:.1f} {py - 6:.1f} {ground + 3.2:.1f}" '
                 f'xyaxes="0.707 0.707 0 -0.35 0.35 0.87"/>\n    </worldbody>', xml, count=1)

    open(args.dst, "w", encoding="utf-8").write(xml)
    print(f"wrote {os.path.relpath(args.dst, ASSETS)} ({os.path.getsize(args.dst)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
