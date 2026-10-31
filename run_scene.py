import os
import sys

import mujoco
import mujoco.viewer


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XML = os.path.join(BASE_DIR, "assets", "demo_v32.xml")


def run(headless=False):
    # 默认直接进入行走演示；--static 保留原来的静态展示场景。
    use_walk = ("--walk" in sys.argv or "--mission" in sys.argv
                or "--static" not in sys.argv)
    if use_walk and not headless:
        program = sys.argv[0]
        args = [x for x in sys.argv[1:] if x not in ("--walk", "--static")]
        if "--mission" not in args:
            # 默认演示：Go2 沿村道按 A* 路线绕障往返巡逻（展示层与物理层同步），
            # G1 停在近端平缓路口。物理层已恢复全部 610 个碰撞代理，
            # 所以看得见的石头也挡得住 —— 不会再穿模，路线由 A* 绕行。
            args = (["--mission", "--loop",
                     "--go2-start", "3.6", "-22", "--go2-goal", "-26", "-44",
                     "--g1-start", "0", "-15", "--g1-goal", "0", "-15"]
                    + args)
        sys.argv = [program] + args
        print("Loading walking scene and robot policies, please wait...", flush=True)
        sys.path.insert(0, os.path.join(BASE_DIR, "assets", "train"))
        import run_scene_walk
        run_scene_walk.main()
        return

    model = mujoco.MjModel.from_xml_path(XML)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    # 先跑 5 秒让废墟、楼板落定，避免打开窗口时看到一堆悬空物体
    for _ in range(2500):
        mujoco.mj_step(model, data)
    mujoco.mj_forward(model, data)

    if headless:
        print("loaded OK: nbody =", model.nbody, "ngeom =", model.ngeom)
        print("settled ok")
        return

    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        viewer.cam.lookat[:] = [0, 0, 20]
        viewer.cam.distance = 90
        viewer.cam.azimuth = 45
        viewer.cam.elevation = 25
        while viewer.is_running():
            mujoco.mj_step(model, data)
            viewer.sync()


if __name__ == "__main__":
    run(headless=("--headless" in sys.argv
                  and "--walk" not in sys.argv
                  and "--mission" not in sys.argv))
