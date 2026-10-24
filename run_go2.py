"""打开/运行宇树 Go2（由 unitree_ros URDF 导入的 MuJoCo 模型）。

    python run_go2.py              # 打开交互窗口（被动模式，可以直接拖拽/看动画）
    python run_go2.py --headless   # 不开窗口，只做加载+站立自检（CI/无显示器时用）
    python run_go2.py --sim 5      # 跑 5 秒物理再退出（打印机身高度）

开场用 home 姿态（大腿 0.9 rad / 小腿 -1.8 rad / 机身 0.27 m），
12 个位置电机 kp=100 会把它稳稳托住。
"""
import argparse
import os
import sys

import mujoco
import mujoco.viewer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.join(BASE_DIR, "assets", "props", "robots", "go2_urdf", "go2_scene.xml")


def build():
    if not os.path.exists(SCENE):
        sys.exit(f"找不到模型：{SCENE}\n先跑 assets/_tools/fetch_go2_urdf.py + import_go2_urdf.py")
    model = mujoco.MjModel.from_xml_path(SCENE)
    data = mujoco.MjData(model)
    # 关键：用 keyframe 的 home 姿态起步，否则腿是伸直零位、站不住
    mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    return model, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true", help="不开窗口，只自检")
    ap.add_argument("--sim", type=float, default=0.0, help="跑 N 秒物理后退出")
    args = ap.parse_args()

    model, data = build()
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "base")
    print(f"Go2 loaded: nq={model.nq} nu={model.nu} mass={model.body_mass.sum():.2f} kg, "
          f"base z={data.xpos[bid][2]:.3f} m")

    if args.sim > 0:
        n = int(args.sim / model.opt.timestep)
        for _ in range(n):
            mujoco.mj_step(model, data)
        print(f"跑完 {args.sim:g} s：base z={data.xpos[bid][2]:.3f} m")
        if args.headless:
            return

    if args.headless:
        print("headless OK")
        return

    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        viewer.cam.lookat[:] = [0.0, 0.0, 0.25]
        viewer.cam.distance = 1.4
        viewer.cam.azimuth = 135
        viewer.cam.elevation = -18
        while viewer.is_running():
            mujoco.mj_step(model, data)
            viewer.sync()


if __name__ == "__main__":
    main()
