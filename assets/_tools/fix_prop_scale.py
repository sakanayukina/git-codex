r"""把场景里明显过大的道具缩回真实尺寸（树桩、废墟块），让近景比例正常。

    python fix_prop_scale.py --in ../demo_v30.xml --out ../demo_v30.xml

规则：
    body 名以 tree_stump 开头        → 缩放 0.42（原尺寸约 1.5 m 高，真实树桩 0.5–0.6 m）
    body 名含 debris/rubble/block 且某边 > 0.5 m → 缩放 0.55（巨型方块 → 瓦砾尺寸）
其它几何不动。只改静态道具，不影响机器人。
"""
import argparse
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)

STUMP = ("tree_stump",)
BULK = ("debris", "rubble", "block", "cone", "barrier")


def scale_size(size_str, f):
    vals = [float(x) for x in size_str.split()]
    return " ".join(f"{v * f:.4f}".rstrip("0").rstrip(".") for v in vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ASSETS, "demo_v30.xml"))
    ap.add_argument("--out", dest="dst", default=None)
    a = ap.parse_args()
    dst = a.dst or a.src

    s = open(a.src, encoding="utf-8").read()
    out = []
    pos = 0
    stack = []
    n_stump = n_bulk = 0

    for m in re.finditer(r"<(/?)(body|geom)\b([^>]*?)(/?)>", s):
        out.append(s[pos:m.start()])
        pos = m.end()
        closing, tag, attrs, selfclose = m.group(1), m.group(2), m.group(3), m.group(4)
        text = m.group(0)

        if tag == "body":
            if closing:
                if stack:
                    stack.pop()
            elif not selfclose:
                nm = re.search(r'name="([^"]*)"', attrs)
                stack.append(nm.group(1) if nm else "")
        elif tag == "geom" and not closing:
            body = stack[-1] if stack else ""
            sm = re.search(r'size="([^"]*)"', attrs)
            if sm and len(sm.group(1).split()) == 3:
                f = 1.0
                if body.startswith(STUMP):
                    f = 0.42
                    n_stump += 1
                elif any(k in body.lower() for k in BULK):
                    if max(float(x) for x in sm.group(1).split()) > 0.5:
                        f = 0.55
                        n_bulk += 1
                if f != 1.0:
                    new_size = scale_size(sm.group(1), f)
                    text = text.replace(f'size="{sm.group(1)}"', f'size="{new_size}"', 1)
        out.append(text)

    out.append(s[pos:])
    open(dst, "w", encoding="utf-8").write("".join(out))
    print(f"缩放：树桩 {n_stump} 个 ×0.42，废墟块 {n_bulk} 个 ×0.55 → {os.path.relpath(dst, ASSETS)}")

    import mujoco
    m = mujoco.MjModel.from_xml_path(dst)
    print(f"校验：nq={m.nq} nu={m.nu} ngeom={m.ngeom}")


if __name__ == "__main__":
    main()
