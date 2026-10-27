"""渲染训练地形上行走的画面（用 ckpt/bc.pt）。"""
import os
import numpy as np
import mujoco
import torch

import env as E
from pngutil import save_rgb
from ppo import ActorCritic
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity

E.SIM_DT, E.DECIM = 0.005, 4


def main():
    png = os.environ["DSH_TERRAIN_PNG"]
    m = mujoco.MjModel.from_xml_string(E.make_xml(png, 100.0, 66.5))
    d = mujoco.MjData(m)
    qadr, dadr, aid = [], [], []
    for jn in E.JOINTS:
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn + "_joint")
        qadr.append(int(m.jnt_qposadr[j])); dadr.append(int(m.jnt_dofadr[j]))
        aid.append(next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == j))
    qadr, dadr, aid = np.array(qadr), np.array(dadr), np.array(aid)
    bb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
    gid = np.array([-1], dtype=np.int32)
    grp = np.array([0, 1, 0, 0, 0, 0], dtype=np.uint8)

    def ground(x, y):
        dist = mujoco.mj_ray(m, d, np.array([x, y, 300.0]), np.array([0.0, 0.0, -1.0]), grp, 1, -1, gid)
        return 300.0 - dist if dist > 0 else 0.0

    x, y = 10.0, -14.0
    d.qpos[0:3] = [x, y, 60.0]
    mujoco.mj_forward(m, d)
    gz = ground(x, y)
    d.qpos[0:3] = [x, y, gz + 0.45]
    d.qpos[3:7] = [1, 0, 0, 0]
    d.qpos[qadr] = DEFAULT
    mujoco.mj_forward(m, d)

    net = ActorCritic(); net.load_state_dict(torch.load("ckpt/bc.pt", map_location="cpu")["net"]); net.eval()
    os.makedirs("shots", exist_ok=True)
    ren = mujoco.Renderer(m, 360, 480)
    cam = mujoco.MjvCamera(); mujoco.mjv_defaultFreeCamera(m, cam)
    cam.distance, cam.azimuth, cam.elevation = 4.5, 135, -16
    target = DEFAULT.copy(); action = np.zeros(12, dtype=np.float32); obs = np.zeros(45, dtype=np.float32)
    shots = {100, 250, 400}
    for k in range(500):
        for _ in range(4):
            q, qd = d.qpos[qadr], d.qvel[dadr]
            d.ctrl[aid] = clip_torque_speed(KP * (target - q) - KD * qd, qd)
            mujoco.mj_step(m, d)
        obs[0:3] = d.qvel[3:6] * 0.25; obs[3:6] = gravity(d.qpos[3:7]); obs[6:9] = [1, 0, 0]
        obs[9:21] = d.qpos[qadr] - DEFAULT; obs[21:33] = d.qvel[dadr] * 0.05; obs[33:45] = action
        with torch.inference_mode():
            mu, _ = net(torch.as_tensor(obs).unsqueeze(0))
        action = mu.numpy()[0]; target = DEFAULT + 0.25 * action
        if k in shots:
            cam.lookat[:] = [float(d.qpos[0]), float(d.qpos[1]), float(d.qpos[2])]
            ren.update_scene(d, camera=cam)
            save_rgb(ren.render(), "shots/terrain_k%03d.png" % k)
            print("shot k=%d 位移 x=%.2f z=%.2f" % (k, d.qpos[0] - x, d.qpos[2]))
    print("总位移 %.2f m, 末 z %.2f" % (d.qpos[0] - x, d.qpos[2]))


if __name__ == "__main__":
    main()
