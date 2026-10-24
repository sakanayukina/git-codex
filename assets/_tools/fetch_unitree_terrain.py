r"""下载 unitree_mujoco 的 terrain_tool（地形生成器）。

    python fetch_unitree_terrain.py

只取 3 个文件（生成器 + 空白场景 + 说明），不 clone 整个仓库：
    assets/_tools/unitree_terrain/
    ├── terrain_generator.py   官方地形生成器（AddBox/AddStairs/AddRoughGround...）
    ├── scene.xml              官方空白场景模板
    ├── readme_zh.md           中文说明（原样保留）
    └── LICENSE                原仓库许可证
"""
import os
import re
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "unitree_terrain")
RAW = "https://raw.githubusercontent.com/unitreerobotics/unitree_mujoco/main"
MIRROR = "https://ghfast.top/"
FILES = {
    "terrain_generator.py": f"{RAW}/terrain_tool/terrain_generator.py",
    "scene.xml": f"{RAW}/terrain_tool/scene.xml",
    "readme_zh.md": f"{RAW}/terrain_tool/readme_zh.md",
    "LICENSE": f"{RAW}/LICENSE",
}


def get(url, tries=5):
    last = None
    for attempt in range(tries):
        for u in (url, MIRROR + url):
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "dsh-fetch"})
                with urllib.request.urlopen(req, timeout=90) as r:
                    b = r.read()
                if b:
                    return b
            except Exception as e:          # noqa: BLE001
                last = e
        time.sleep(1.0 + attempt)
    raise RuntimeError(f"失败 {url}: {last}")


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, url in FILES.items():
        p = os.path.join(OUT, name)
        b = get(url)
        open(p, "wb").write(b)
        print(f"  {name:<22} {len(b)/1024:7.1f} KB")

    gen = open(os.path.join(OUT, "terrain_generator.py"), encoding="utf-8").read()
    fns = re.findall(r"^\s*def (\w+)\(", gen, re.M)
    print("\n生成器里的方法:")
    for f in fns:
        print(f"   def {f}(...)")
    lic = open(os.path.join(OUT, "LICENSE"), encoding="utf-8", errors="ignore").read()
    print("\n许可证首行:", lic.strip().splitlines()[0])


if __name__ == "__main__":
    main()
