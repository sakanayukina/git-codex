"""打开/运行宇树 G1 人形机器人（官方 g1_29dof.xml + STL 网格导入版）。

    python run_g1.py                # 打开窗口（基座固定，站着不动）
    python run_g1.py --free         # 打开带 freejoint 的版本（没有控制器会摔，看个真）
    python run_g1.py --headless     # 只加载自检
    python run_g1.py --sim 2        # 跑 2 秒物理后打印骨盆高度

两个场景的区别：
    g1_scene.xml  基座焊在世界坐标系 —— 当场景 NPC / 摆拍用，绝不会倒
    g1_free.xml   有 freejoint —— 可以做物理/RL，但需要自己的平衡控制器
"""
import argparse
import os
import sys

import mujoco
import mujoco.viewer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.join(BASE_DIR, "assets", "props", "robots", "g1")


def build(free):
    path = os.path.join(ROBOT, "g1_free.xml" if free else "g1_scene.xml")
    if not os.path.exists(path):
        sys.exit(f"找不到模型：{path}\n先跑 assets/_tools/import_g1.py")
    model = mujoco.MjModel.from_xml_path(path)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    return model, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--free", action="store_true", help="用带 freejoint 的版本")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--sim", type=float, default=0.0, help="跑 N 秒物理后退出/再开窗")
    args = ap.parse_args()

    model, data = build(args.free)
    pel = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
    print(f"G1 loaded ({'free' if args.free else 'fixed'}): nq={model.nq} nu={model.nu} "
          f"mass={model.body_mass.sum():.1f} kg, pelvis z={data.xpos[pel][2]:.3f} m")

    if args.sim > 0:
        n = int(args.sim / model.opt.timestep)
        for _ in range(n):
            mujoco.mj_step(model, data)
        print(f"跑完 {args.sim:g} s：pelvis z={data.xpos[pel][2]:.3f} m")
        if args.headless:
            return

    if args.headless:
        print("headless OK")
        return

    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        viewer.cam.lookat[:] = [0.0, 0.0, 0.7]
        viewer.cam.distance = 2.6
        viewer.cam.azimuth = 135
        viewer.cam.elevation = -12
        while viewer.is_running():
            mujoco.mj_step(model, data)
            viewer.sync()


if __name__ == "__main__":
    main()
