r"""下载 unitree_ros 的 Go2 URDF 描述（urdf + COLLADA 网格）。

    python fetch_go2_urdf.py            # 下载到 assets/props/robots/go2_urdf/
    python fetch_go2_urdf.py --check    # 只看清单
"""
import argparse
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
OUT = os.path.join(ASSETS, "props", "robots", "go2_urdf")

BASE = "https://raw.githubusercontent.com/unitreerobotics/unitree_ros/master/robots/go2_description"
API = "https://api.github.com/repos/unitreerobotics/unitree_ros/contents/robots/go2_description"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dsh-fetch"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    meshes = [a for a in json.loads(get(f"{API}/meshes").decode()) if a["name"].endswith(".dae")]
    total = sum(m["size"] for m in meshes)
    print(f"COLLADA 网格 {len(meshes)} 个, {total/1e6:.1f} MB")
    for m in sorted(meshes, key=lambda x: -x["size"]):
        print(f"   {m['size']/1e6:6.2f} MB  {m['name']}")
    if args.check:
        return

    os.makedirs(os.path.join(OUT, "meshes"), exist_ok=True)
    p = os.path.join(OUT, "go2_description.urdf")
    open(p, "wb").write(get(f"{BASE}/urdf/go2_description.urdf"))
    print(f"  urdf {os.path.getsize(p)/1024:.1f} KB")
    for m in meshes:
        p = os.path.join(OUT, "meshes", m["name"])
        if os.path.exists(p) and os.path.getsize(p) == m["size"]:
            continue
        open(p, "wb").write(get(f"{BASE}/meshes/{m['name']}"))
        print(f"  meshes/{m['name']:<20} {os.path.getsize(p)/1e6:6.2f} MB")
    print(f"done -> {os.path.relpath(OUT, ASSETS)}")


if __name__ == "__main__":
    main()
