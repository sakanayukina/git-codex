r"""补齐 g1_12dof 模型引用但本地缺失的 STL（走可用的 GitHub 镜像）。

    python fix_g1_12dof_meshes.py
"""
import os
import re
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
G1 = os.path.join(os.path.dirname(HERE), "props", "robots", "g1")
MSD = os.path.join(G1, "meshes")
MODEL = os.path.join(G1, "g1_12dof_official.xml")

MIRRORS = ("https://ghproxy.net/https://raw.githubusercontent.com/",
           "https://gh-proxy.com/https://raw.githubusercontent.com/")
REPO = "unitreerobotics/unitree_rl_gym/main/resources/robots/g1_description/meshes/"


def fetch(name):
    for m in MIRRORS:
        for _ in range(2):
            try:
                u = m + REPO + name
                d = urllib.request.urlopen(urllib.request.Request(
                    u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
                if d[:2] in (b"PK", b"so") or len(d) > 1000:
                    return d
            except Exception:
                time.sleep(1.0)
    return None


def main():
    s = open(MODEL, encoding="utf-8").read()
    need = sorted(set(re.findall(r'file="([^"]+\.STL)"', s)))
    miss = [n for n in need if not os.path.exists(os.path.join(MSD, n))]
    print(f"引用 {len(need)} 个 STL，缺 {len(miss)} 个")
    ok = 0
    for n in miss:
        d = fetch(n)
        if d:
            open(os.path.join(MSD, n), "wb").write(d)
            ok += 1
            print(f"  + {n} {len(d)/1024:.0f} KB")
        else:
            print(f"  ! {n} 下载失败")
    print(f"补齐 {ok}/{len(miss)}")


if __name__ == "__main__":
    main()
