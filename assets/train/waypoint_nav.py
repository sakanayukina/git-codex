"""航点导航：闭环控制（前进 + 转向）走到目标点，测「长时行动」能力。

转向通道已实测：obs[8] = yaw_rate × 0.25，**符号相反**（正指令→右转），跟踪率约 50%，
零指令有 +0.15 rad/s 左右的漂移 → 必须用闭环反馈修正。

    python waypoint_nav.py --robot go2 --xml ../village_walk_final.xml --goal 12 -20 --seconds 90
"""
import argparse
import os
import sys

import mujoco
import numpy as np
import torch

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "..", "_tools"))
from nav_grid import NavGrid  # noqa: E402
from run_ref import DEFAULT, KP, KD, clip_torque_speed, gravity  # noqa: E402

GO2_JOINTS = ["FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
              "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
              "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
              "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint"]


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def yaw_of(q):
    w, x, y, z = q
    return np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", default=os.path.join(BASE, "..", "village_walk_final.xml"))
    ap.add_argument("--policy", default=os.path.join(BASE, "pretrained", "go2_cts_vanilla2_103.5k_0.5786.pt"))
    ap.add_argument("--at", nargs=2, type=float, default=[1.0, -20.0])
    ap.add_argument("--goal", nargs=2, type=float, default=[14.0, -20.0])
    ap.add_argument("--seconds", type=float, default=90.0)
    ap.add_argument("--vx", type=float, default=1.0, help="前进指令（obs[6] = vx*2）")
    ap.add_argument("--kp-yaw", type=float, default=1.2)
    ap.add_argument("--yaw-sign", type=float, default=1.0,
                    help="闭环转向符号；当前策略实测为 +1")
    ap.add_argument("--tolerance", type=float, default=1.0)
    ap.add_argument("--astar", action="store_true",
                    help="先用 NavGrid/A* 规划，再串联多航点实走")
    ap.add_argument("--grid-scene", default=os.path.join(BASE, "..", "village_duo.xml"))
    ap.add_argument("--max-slope", type=float, default=10.0)
    ap.add_argument("--slope-soft", type=float, default=8.0)
    ap.add_argument("--grid-res", type=float, default=1.0)
    ap.add_argument("--robot-radius", type=float, default=0.35)
    ap.add_argument("--waypoint-tolerance", type=float, default=0.6)
    a = ap.parse_args()

    goal = np.array(a.goal, dtype=float)
    start = np.array(a.at, dtype=float)
    plan = None
    if a.astar:
        grid = NavGrid(scene=a.grid_scene, res=a.grid_res,
                       robot_radius=a.robot_radius)
        plan, message = grid.plan(
            start, goal, max_slope=a.max_slope, slope_soft=a.slope_soft)
        if plan is None:
            print("A* 规划失败:", message)
            return
        path = [np.asarray(point, dtype=float) for point in plan["points"]]
        print("A*: %.1f m, %d waypoints, max slope %.1f deg"
              % (plan["length"], len(path), plan["max_slope"]))
    else:
        path = [goal]

    m = mujoco.MjModel.from_xml_path(a.xml)
    m.opt.timestep = 0.005
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)

    bb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "base")
    bj = next(j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE
              and int(m.jnt_bodyid[j]) == bb)
    bq, bd = int(m.jnt_qposadr[bj]), int(m.jnt_dofadr[bj])
    q, dof, act = [], [], []
    for jn in GO2_JOINTS:
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn)
        q.append(int(m.jnt_qposadr[j])); dof.append(int(m.jnt_dofadr[j]))
        act.append(next(i for i in range(m.nu) if int(m.actuator_trnid[i][0]) == j))
    q, dof, act = np.array(q), np.array(dof), np.array(act)

    hf = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
    gid = np.array([-1], dtype=np.int32); grp = np.ones(6, dtype=np.uint8)

    def ground(x, y):
        for dx, dy in [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2)]:
            dist = mujoco.mj_ray(m, d, np.array([x + dx, y + dy, 300.0]),
                                 np.array([0, 0, -1.0]), grp, 1, -1, gid)
            if dist > 0 and int(gid[0]) == hf:
                return 300.0 - dist
        return 5.0

    gz = ground(*a.at)
    d.qpos[bq:bq+3] = [a.at[0], a.at[1], gz + 0.45]
    d.qpos[bq+3:bq+7] = [1, 0, 0, 0]
    d.qpos[q] = DEFAULT
    mujoco.mj_forward(m, d)

    net = torch.jit.load(a.policy); net.eval()
    obs = np.zeros(45, dtype=np.float32); a_ = np.zeros(12, dtype=np.float32); tgt = DEFAULT.copy()

    waypoint = 0
    while (waypoint < len(path)
           and np.linalg.norm(path[waypoint] - start) < a.waypoint_tolerance):
        waypoint += 1
    best = 0.0
    reached_at = None
    fell_at = None

    n = int(a.seconds / 0.02)
    for k in range(n):
        pos = np.array([d.qpos[bq], d.qpos[bq+1]])
        tolerance = (a.tolerance if waypoint == len(path) - 1
                     else a.waypoint_tolerance)
        while (waypoint < len(path)
               and np.linalg.norm(path[waypoint] - pos) < tolerance):
            waypoint += 1
        if waypoint >= len(path):
            reached_at = k * 0.02
            break
        target = path[waypoint]
        to_goal = target - pos
        dist_goal = float(np.linalg.norm(to_goal))
        best = max(best, float(np.linalg.norm(pos - start)))

        err = wrap(np.arctan2(to_goal[1], to_goal[0]) - yaw_of(d.qpos[bq+3:bq+7]))
        yaw_cmd = float(np.clip(a.yaw_sign * a.kp_yaw * err, -1.5, 1.5))
        # 航点前减速，转向误差大时降低前进速度。
        vx = a.vx if dist_goal > 1.5 else a.vx * max(dist_goal / 1.5, 0.35)
        vx *= max(0.25, np.cos(err) ** 2)

        for _ in range(4):
            d.ctrl[act] = clip_torque_speed(KP * (tgt - d.qpos[q]) - KD * d.qvel[dof], d.qvel[dof])
            mujoco.mj_step(m, d)

        up = float(d.xmat[bb].reshape(3, 3)[2, 2])
        if up < 0.5:
            fell_at = k * 0.02
            break

        obs[0:3] = d.qvel[bd+3:bd+6] * 0.25
        obs[3:6] = gravity(d.qpos[bq+3:bq+7])
        obs[6:9] = [vx, 0.0, yaw_cmd * 0.25]
        obs[9:21] = d.qpos[q] - DEFAULT
        obs[21:33] = d.qvel[dof] * 0.05
        obs[33:45] = a_
        with torch.inference_mode():
            out = net(torch.as_tensor(obs).unsqueeze(0))
        a_ = (out[0].numpy() if isinstance(out, tuple) else out.numpy())[0]
        tgt = DEFAULT + 0.25 * a_

    pos = np.array([d.qpos[bq], d.qpos[bq+1]])
    final_dist = float(np.linalg.norm(pos - start))
    remain = float(np.linalg.norm(goal - pos))
    remaining_path = (float(np.linalg.norm(path[-1] - pos)) if path else 0.0)
    status = ("到达路径终点 @ %.1f s" % reached_at) if reached_at else (
        ("摔倒 @ %.1f s" % fell_at) if fell_at else "超时未到达")
    print("起点 (%.1f, %.1f) → 目标 (%.1f, %.1f)"
          % (a.at[0], a.at[1], goal[0], goal[1]))
    print("结果: %s | 里程 %.2f m | 航点 %d/%d | 距场地目标 %.2f m | 平均 %.2f m/s"
          % (status, final_dist, min(waypoint, len(path)), len(path), remain,
             final_dist / max((reached_at or a.seconds), 1e-6)))


if __name__ == "__main__":
    main()
