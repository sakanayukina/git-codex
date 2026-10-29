"""诊断：把村里非机器人 body 的质量清零，看机器人是否能走。"""
import mujoco, numpy as np, torch
from ppo import ActorCritic
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity

J = ["FL_hip","FL_thigh","FL_calf","FR_hip","FR_thigh","FR_calf",
     "RL_hip","RL_thigh","RL_calf","RR_hip","RR_thigh","RR_calf"]


def run(xml, zero_mass=False, seconds=8, at=(12.0, -18.0)):
    m = mujoco.MjModel.from_xml_path(xml)
    m.opt.timestep = 0.005
    m.opt.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    m.opt.cone = mujoco.mjtCone.mjCONE_PYRAMIDAL
    m.opt.impratio = 1.0
    bb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
    if zero_mass:
        robot = set()
        for i in range(m.nbody):
            p = i
            while p != 0:
                if p == bb:
                    robot.add(i); break
                p = int(m.body_parentid[p])
        for i in range(1, m.nbody):
            if i not in robot:
                m.body_mass[i] = 1e-6
    d = mujoco.MjData(m)
    qadr, dadr, aid = [], [], []
    for jn in J:
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn + "_joint")
        qadr.append(int(m.jnt_qposadr[j])); dadr.append(int(m.jnt_dofadr[j]))
        aid.append(next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == j))
    qadr, dadr, aid = np.array(qadr), np.array(dadr), np.array(aid)
    bj = next(j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE
              and int(m.jnt_bodyid[j]) == bb)
    bq, bd = int(m.jnt_qposadr[bj]), int(m.jnt_dofadr[bj])
    hf = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    d.qpos[bq:bq+3] = [512.0, -18.0, -800.0]
    mujoco.mj_forward(m, d)
    gid = np.array([-1], dtype=np.int32); grp = np.ones(6, dtype=np.uint8)
    gz = 5.0
    for dx, dy in [(0,0),(2,0),(-2,0),(0,2),(0,-2)]:
        dist = mujoco.mj_ray(m, d, np.array([at[0]+dx, at[1]+dy, 300.0]), np.array([0,0,-1.0]), grp, 1, -1, gid)
        if dist > 0 and int(gid[0]) == hf:
            gz = 300.0 - dist; break
    d.qpos[bq:bq+3] = [at[0], at[1], gz + 0.45]
    d.qpos[bq+3:bq+7] = [1,0,0,0]
    d.qpos[qadr] = DEFAULT
    mujoco.mj_forward(m, d)
    net = ActorCritic(); net.load_state_dict(torch.load("ckpt/bc.pt", map_location="cpu")["net"]); net.eval()
    target = DEFAULT.copy(); action = np.zeros(12, dtype=np.float32); obs = np.zeros(45, dtype=np.float32)
    x0 = float(d.qpos[bq]); ys = float(d.qpos[bq+1])
    n = int(seconds / 0.02)
    for k in range(n):
        for _ in range(4):
            q, qd = d.qpos[qadr], d.qvel[dadr]
            d.ctrl[aid] = clip_torque_speed(KP*(target-q) - KD*qd, qd)
            mujoco.mj_step(m, d)
        obs[0:3] = d.qvel[bd+3:bd+6]*0.25
        obs[3:6] = gravity(d.qpos[bq+3:bq+7])
        obs[6:9] = [1,0,0]
        obs[9:21] = d.qpos[qadr] - DEFAULT
        obs[21:33] = d.qvel[dadr]*0.05
        obs[33:45] = action
        with torch.inference_mode():
            mu, _ = net(torch.as_tensor(obs).unsqueeze(0))
        action = mu.numpy()[0]; target = DEFAULT + 0.25*action
        if float(d.xmat[bb].reshape(3,3)[2,2]) < 0.5:
            print("  %s 倒地于 %.1f s" % (xml.split('/')[-1], k*0.02)); break
    dist_xy = float(np.hypot(d.qpos[bq]-x0, d.qpos[bq+1]-ys))
    print("%-28s zero_mass=%-5s 位移 %.2f m, 末 z %.2f" % (xml.split('/')[-1], zero_mass, dist_xy, d.qpos[bq+2]))


if __name__ == "__main__":
    run("../village_walk_final.xml", False)
    run("../village_walk2.xml", False)
    run("../village_walk2.xml", True)
