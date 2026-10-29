"""把 village_walk_final.xml 里的 Go2 再复制一台 → village_duo_go2x2.xml。

两台 Go2 共享网格资产（mesh 名不变），只改 body/joint/motor 名（加 2 后缀），
放在同一 worldbody，用于验证“同场物理碰撞”（step 3）。

    python make_village_duo_go2x2.py
"""
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "..")
SRC = os.path.join(ASSETS, "village_walk_final.xml")
OUT = os.path.join(ASSETS, "village_duo_go2x2.xml")

LEGS = ["FL", "FR", "RL", "RR"]
SEGS = ["hip", "thigh", "calf"]


def extract_body(s):
    """从第一个 <body name="base" 取到配对的 </body>，跳过 <!-- --> 注释里的标签。"""
    start = s.index('<body name="base"')
    i = start
    depth = 0
    in_comment = False
    while i < len(s):
        if s.startswith("<!--", i):
            in_comment = True
            i += 4
            continue
        if in_comment:
            if s.startswith("-->", i):
                in_comment = False
                i += 3
            else:
                i += 1
            continue
        if s.startswith("<body", i):
            depth += 1
            i += 5
        elif s.startswith("</body>", i):
            depth -= 1
            if depth == 0:
                return s[start:i + len("</body>")]
            i += len("</body>")
        else:
            i += 1
    raise SystemExit("body 未闭合")


def main():
    s = open(SRC, encoding="utf-8").read()

    body = extract_body(s)

    # 改名（先关节，再 body，避免前缀误伤）
    for L in LEGS:
        for S in SEGS:
            body = body.replace('name="%s_%s_joint"' % (L, S), 'name="%s2_%s_joint"' % (L, S))
    for L in LEGS:
        for S in SEGS:
            body = body.replace('name="%s_%s"' % (L, S), 'name="%s2_%s"' % (L, S))
    body = body.replace('<body name="base"', '<body name="base2"', 1)
    body = body.replace('<freejoint name="root"/>', '<freejoint name="root2"/>', 1)
    for g in ("base_box", "base_cyl1", "base_sphere1"):
        body = body.replace('name="%s"' % g, 'name="%s2"' % g, 1)

    # 第二台出生点：放到第一台正前方 4 m，走相反方向即可相撞
    body = body.replace('pos="12.00 -18.00 5.40"', 'pos="4.00 -20.00 5.40"', 1)

    # 电机块复制
    act = re.search(r"<actuator>(.*?)</actuator>", s, re.S).group(1)
    act2 = act
    for L in LEGS:
        for S in SEGS:
            act2 = act2.replace('name="%s_%s"' % (L, S), 'name="%s2_%s"' % (L, S))
            act2 = act2.replace('joint="%s_%s_joint"' % (L, S), 'joint="%s2_%s_joint"' % (L, S))

    out = s
    out = out.replace("</worldbody>", body + "\n  </worldbody>", 1)
    out = out.replace("</actuator>", act2 + "\n  </actuator>", 1)

    open(OUT, "w", encoding="utf-8").write(out)
    print("生成 %s" % OUT)


if __name__ == "__main__":
    main()
