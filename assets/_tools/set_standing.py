r"""给合并后的场景补一个 standing keyframe（Go2 用 home 姿态，G1 保持固定基座零位）。

    python set_standing.py --xml ../demo_v29.xml

为什么需要单独一步：村子的 qpos 有 651 维（Codex 的 collapse_* 结构每个都是 free joint），
机器人自带的 keyframe 只有 19 维，合并后必然尺寸不符。所以按整场 nq 重新生成一条。
"""
import argparse
import os
import re

import mujoco

STAND = {"hip": 0.0, "thigh": 0.9, "calf": -1.8}      # Go2 home 姿态
GO2_JOINTS = ("FL_hip", "FL_thigh", "FL_calf", "FR_hip", "FR_thigh", "FR_calf",
              "RL_hip", "RL_thigh", "RL_calf", "RR_hip", "RR_thigh", "RR_calf")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_v29.xml"))
    args = ap.parse_args()

    m = mujoco.MjModel.from_xml_path(args.xml)
    d = mujoco.MjData(m)
    qpos = list(m.qpos0)
    ctrl = [0.0] * m.nu

    for jn in GO2_JOINTS:
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn + "_joint")
        if jid < 0:
            continue
        key = "hip" if "hip" in jn else ("calf" if "calf" in jn else "thigh")
        qpos[m.jnt_qposadr[jid]] = STAND[key]
    # 位置电机的目标 = 姿态角
    for a in range(m.nu):
        an = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, a) or ""
        jn = an.replace("_pos", "")
        if jn in [x + "_joint" for x in GO2_JOINTS]:
            key = "hip" if "hip" in jn else ("calf" if "calf" in jn else "thigh")
            ctrl[a] = STAND[key]

    xml = open(args.xml, encoding="utf-8").read()

    # ---- 按真实地形把机器人落到位（演示场景地形不平，靠"集结点 z + 常数"会浮空）
    import numpy as np
    drops = {}
    for body_name, stand in (("go2_base", 0.27), ("pelvis", 0.862)):
        bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, body_name)
        if bid < 0:
            continue
        x, y = float(m.body_pos[bid][0]), float(m.body_pos[bid][1])
        gid = np.array([-1], dtype=np.int32)
        dist = mujoco.mj_ray(m, d, np.array([x, y, 300.0]), np.array([0, 0, -1.0]),
                             None, 1, bid, gid)
        if dist <= 0:
            continue
        target = (300.0 - dist) + stand
        drops[body_name] = (x, y, target)
        print(f"  {body_name}: 地形 z={target - stand:.3f} → 目标机身 z={target:.3f}")
    for body_name, (x, y, z) in drops.items():
        xml = re.sub(rf'(<body name="{body_name}"[^>]*?pos="[-\d.]+ [-\d.]+ )([-\d.]+)(")',
                     lambda mm: f"{mm.group(1)}{z:.3f}{mm.group(3)}", xml, count=1)

    xml = re.sub(r"\s*<keyframe>.*?</keyframe>", "", xml, flags=re.S)
    qs = " ".join(f"{v:.4f}" for v in qpos)
    cs = " ".join(f"{v:.4f}" for v in ctrl)
    xml = xml.replace("</mujoco>",
                      f'  <keyframe>\n    <key name="home" qpos="{qs}" ctrl="{cs}"/>\n'
                      f"  </keyframe>\n</mujoco>", 1)
    open(args.xml, "w", encoding="utf-8").write(xml)
    print(f"keyframe 写入：nq={m.nq} nu={m.nu}")

    # 自检
    m2 = mujoco.MjModel.from_xml_path(args.xml)
    d2 = mujoco.MjData(m2)
    mujoco.mj_resetDataKeyframe(m2, d2, 0)
    b = mujoco.mj_name2id(m2, mujoco.mjtObj.mjOBJ_BODY, "go2_base")
    for _ in range(1000):
        mujoco.mj_step(m2, d2)
    print(f"静置 2 s 后 go2_base z = {d2.xpos[b][2]:.3f} m（目标 ≈ 地面 1.45 + 0.27）")


if __name__ == "__main__":
    main()
