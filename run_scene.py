import sys

import mujoco
import mujoco.viewer


XML = r"C:\Users\18967\Desktop\git\assets\demo_rescue_scene.xml"


def run(headless=False):
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
    run(headless="--headless" in sys.argv)
