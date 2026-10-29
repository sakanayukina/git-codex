"""合并 Go2 + G1 到同一个 MuJoCo 世界：village_duo.xml

    python make_village_duo.py

从 village_walk_final.xml（Go2 + 地形 + 610 碰撞代理）为底，
把 g1_village_final.xml 里的 G1 机器人（default 类、mesh 资产、body 子树、12 电机）注入进去。
两台机器人共享同一个 mjModel / 求解器 / 接触。
"""
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "..")
GO2 = os.path.join(ASSETS, "village_walk_final.xml")
G1 = os.path.join(ASSETS, "g1_village_final.xml")
OUT = os.path.join(ASSETS, "village_duo.xml")


def extract_balanced(s, open_pat, close="</body>"):
    """从 <body name=...> 起，取到与之配对的 </body>。"""
    m = re.search(open_pat, s)
    if not m:
        raise SystemExit("找不到 " + open_pat)
    start = m.start()
    depth = 0
    i = start
    while i < len(s):
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
    go2 = open(GO2, encoding="utf-8").read()
    g1 = open(G1, encoding="utf-8").read()

    # 1) G1 的 mesh 资产（把相对 meshdir 的 file 改成相对 XML 目录的路径，避免设全局 meshdir 后劫持 hfield/texture 解析）
    def fix_mesh(m):
        t = " ".join(m.split())
        t = re.sub(r'file="([^"]+)"', r'file="props/robots/g1/meshes/\1"', t)
        return t
    meshes = re.findall(r"<mesh[^>]*/>", g1)
    mesh_block = "\n    ".join(fix_mesh(m) for m in meshes)

    # 2) G1 的 body 子树（pelvis 根）；给 12 个腿关节内联官方默认参数
    #    （damping=0.001 armature=0.01 frictionloss=0.1），避免与 Go2 顶层默认冲突。
    body = extract_balanced(g1, r'<body\s+name="pelvis"[^>]*>')
    body = re.sub(r'<joint\s+name="', '<joint damping="0.001" armature="0.01" frictionloss="0.1" name="', body)

    # 3) G1 的 12 个 motor
    act = re.search(r"<actuator>(.*?)</actuator>", g1, re.S).group(1)
    act = "\n".join(" ".join(l.split()) for l in act.strip().splitlines() if l.strip())

    out = go2
    # 统一 timestep=0.001（Go2 20 子步、G1 20 子步 → 都是 0.02 s 控制周期）
    out = re.sub(r'<option\s+timestep="[^"]*"',
                 '<option timestep="0.001"', out, count=1)
    # mesh 资产塞进 <asset>
    out = out.replace("</asset>", mesh_block + "\n  </asset>", 1)
    # G1 body 塞进 worldbody
    out = out.replace("</worldbody>", body + "\n  </worldbody>", 1)
    # G1 motor 塞进 actuator
    out = out.replace("</actuator>", act + "\n  </actuator>", 1)

    open(OUT, "w", encoding="utf-8").write(out)
    print("生成 %s" % OUT)


if __name__ == "__main__":
    main()
