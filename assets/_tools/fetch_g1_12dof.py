r"""下载官方 12 自由度 G1 模型（策略 motion.pt 就是在它上面训的）。

    python fetch_g1_12dof.py

写到 assets/props/robots/g1/g1_12dof_official.xml（meshdir 指回已有的 meshes/）。
网络不稳时会自动换 host 重试；三个源都失败就报错退出。
"""
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "props", "robots", "g1", "g1_12dof_official.xml")

SOURCES = [
    "https://raw.githubusercontent.com/unitreerobotics/unitree_rl_gym/main/"
    "resources/robots/g1_description/g1_12dof.xml",
    "https://cdn.jsdelivr.net/gh/unitreerobotics/unitree_rl_gym@main/"
    "resources/robots/g1_description/g1_12dof.xml",
    "https://ghfast.top/https://raw.githubusercontent.com/unitreerobotics/"
    "unitree_rl_gym/main/resources/robots/g1_description/g1_12dof.xml",
    "https://raw.githubusercontent.com/unitreerobotics/unitree_ros/master/"
    "robots/g1_description/g1_12dof.xml",
]


def main():
    last = None
    for url in SOURCES:
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                if b"<mujoco" not in data:
                    raise ValueError("不是 MJCF")
                open(OUT, "wb").write(data)
                print(f"OK {len(data)} bytes <- {url.split('/')[2]}")
                import re
                txt = data.decode("utf-8", "ignore")
                n = len(re.findall(r"<joint ", txt))
                act = len(re.findall(r"<motor ", txt))
                print(f"  关节 {n} 个、motor {act} 个 → {os.path.basename(OUT)}")
                print("  下一步：把它的 meshdir 改成 meshes/，再跑 g1_policy.py --xml 指向它")
                return
            except Exception as e:          # noqa: BLE001
                last = e
                time.sleep(1.5)
        print(f"fail {url.split('/')[2]}: {type(last).__name__}")
    raise SystemExit(f"全部源失败：{last}")


if __name__ == "__main__":
    main()
