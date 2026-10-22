r"""给"只有视觉几何"的房屋/废墟补不可见碰撞外壳（group=3，不渲染但会挡）。

    python add_collision.py --xml ..\demo_v7.xml            # 报告
    python add_collision.py --xml ..\demo_v7.xml --apply    # 就地写入（留 .bak）

规格来自 buildings.json 的 plots：
    "collision": "walls" | "none"
    "collision_box": [宽, 进深, 高, 门洞宽]    # 局部尺寸，缺省用 size + 1.3 m 门洞
"""
import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def shell_body(pid, x, y, z, yaw, w, d, h, door, th=0.18):
    seg = max(0.05, (w / 2 - door / 2) / 2)
    parts = [f'<body name="{pid}_collision" pos="{x:.2f} {y:.2f} {z:.3f}" euler="0 0 {yaw:.1f}">']
    if door > 0:
        for s in (-1, 1):
            parts.append(f'<geom type="box" size="{seg:.2f} {th:.2f} {h / 2:.2f}" '
                         f'pos="{s * (door / 2 + seg):.2f} {-d / 2:.2f} {h / 2:.2f}" group="3"/>')
        parts.append(f'<geom type="box" size="{door / 2:.2f} {th:.2f} 0.55" '
                     f'pos="0 {-d / 2:.2f} {h - 0.55:.2f}" group="3"/>')
    else:
        parts.append(f'<geom type="box" size="{w / 2:.2f} {th:.2f} {h / 2:.2f}" '
                     f'pos="0 {-d / 2:.2f} {h / 2:.2f}" group="3"/>')
    parts.append(f'<geom type="box" size="{w / 2:.2f} {th:.2f} {h / 2:.2f}" '
                 f'pos="0 {d / 2:.2f} {h / 2:.2f}" group="3"/>')
    for s in (-1, 1):
        parts.append(f'<geom type="box" size="{th:.2f} {d / 2:.2f} {h / 2:.2f}" '
                     f'pos="{s * w / 2:.2f} 0 {h / 2:.2f}" group="3"/>')
    parts.append("</body>")
    return "".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=os.path.join(ASSETS, "demo_v7.xml"))
    ap.add_argument("--config", default=os.path.join(ASSETS, "buildings.json"))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    xml = open(args.xml, encoding="utf-8").read()

    added = []
    for p in cfg["plots"]:
        pid = p["id"]
        if p.get("collision") == "none":
            continue
        if f'name="{pid}_collision"' in xml:
            print(f"  {pid}: already has collision shell")
            continue
        if not (p.get("model") or "").strip():
            continue          # 程序化房子自带实心墙，不用补
        box = p.get("collision_box") or [p["size"][0], p["size"][1], p["size"][2], 1.3]
        w, d, h, door = (list(box) + [0])[:4]
        # 地面高度直接读场景里那栋房子的 body z（它就是按地形最低角摆的）
        m = re.search(rf'<body name="{pid}" pos="[-\d.]+ [-\d.]+ ([-\d.]+)"', xml)
        gz = float(m.group(1)) if m else p.get("ground_z", 0.0)
        added.append(shell_body(pid, p["x"], p["y"], gz, p["yaw"], w, d, h, door))
        print(f"  {pid}: shell {w:.1f} x {d:.1f} x {h:.1f} m, door {door:.1f} m, z={gz:.2f}")

    if not added:
        print("nothing to add")
        return
    if not args.apply:
        print(f"(dry run; {len(added)} shells, add --apply)")
        return

    backup = args.xml + ".bak"
    open(backup, "w", encoding="utf-8").write(xml)
    xml = xml.replace("</worldbody>", "".join(added) + "</worldbody>", 1)
    open(args.xml, "w", encoding="utf-8").write(xml)
    print(f"wrote {os.path.relpath(args.xml, ASSETS)} (backup: {os.path.basename(backup)})")


if __name__ == "__main__":
    main()
