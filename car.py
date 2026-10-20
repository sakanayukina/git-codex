import mujoco
import mujoco.viewer
import time
import ikpy.chain
import transforms3d as tf
import numpy as np
from scipy.spatial.transform import Rotation as R, Slerp

def car():
    xml_path = r'C:\Users\18967\Desktop\mujoco-3.15.0-windows-x86_64\model\car\car.xml'
    model = mujoco.MjModel.from_xml_path(xml_path)
    data = mujoco.MjData(model)

    print("nctrl =", model.nu)

    data.ctrl[0] = 0.001
    data.ctrl[1] = 0.001

    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running():
            mujoco.mj_step(model, data)
            viewer.sync()


if __name__ == "__main__":
    car()
