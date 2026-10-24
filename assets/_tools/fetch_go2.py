r"""下载 MuJoCo Menagerie 的 Unitree Go2 MJCF（含 OBJ 网格）。

    python fetch_go2.py                # 下到 assets/props/robots/go2/
    python fetch_go2.py --check        # 只列清单，不下载

走 raw.githubusercontent.com；本机 PowerShell 的 TLS 会报 SEC_E_NO_CREDENTIALS，
所以用 Python 的 urllib（anaconda base 有完整证书链）。
"""
import argparse
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
OUT = os.path.join(ASSETS, "props", "robots", "go2")

RAW = "https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/main/unitree_go2"
API = "https://api.github.com/repos/google-deepmind/mujoco_menagerie/contents/unitree_go2"

# 只要 MJCF + 网格，不要 png/mjx
FILES = ["go2.xml", "scene.xml", "LICENSE", "README.md"]


def get(url, binary=True):
    req = urllib.request.Request(url, headers={"User-Agent": "dsh-fetch"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    # 网格清单从 GitHub API 拿，避免手写文件名
    assets = json.loads(get(f"{API}/assets").decode())
    names = [a["name"] for a in assets if a["name"].endswith(".obj")]
    total = sum(a["size"] for a in assets if a["name"].endswith(".obj"))
    print(f"assets: {len(names)} 个 OBJ, {total/1e6:.1f} MB")
    for a in sorted(assets, key=lambda x: -x["size"])[:5]:
        print(f"   {a['size']/1e6:6.2f} MB  {a['name']}")
    if args.check:
        return

    os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)
    for f in FILES:
        p = os.path.join(OUT, f)
        open(p, "wb").write(get(f"{RAW}/{f}"))
        print(f"  {f:<12} {os.path.getsize(p)/1024:8.1f} KB")
    for n in names:
        p = os.path.join(OUT, "assets", n)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            continue
        open(p, "wb").write(get(f"{RAW}/assets/{n}"))
        print(f"  assets/{n:<24} {os.path.getsize(p)/1e6:6.2f} MB")
    print(f"done -> {os.path.relpath(OUT, ASSETS)}")


if __name__ == "__main__":
    main()
