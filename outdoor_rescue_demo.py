import sys

import mujoco
import mujoco.viewer
import numpy as np


def terrain_height(x, y):
    h = 1.3 * np.clip((-x + 4.5) / 9.0, 0.0, 1.0)
    h += 0.015 * np.sin(1.5 * x) * np.cos(1.2 * y)
    return h


def build_xml():
    n = 40
    xs = np.linspace(-5, 5, n)
    ys = np.linspace(-5, 5, n)
    xx, yy = np.meshgrid(xs, ys)
    heights = terrain_height(xx, yy)
    hfield_txt = "\n".join(" ".join(f"{v:.3f}" for v in row) for row in heights)

    rock_xy = [(-4.0, -0.5), (-4.0, 0.5), (-4.2, 0.0), (-3.9, 1.0)]
    rock_bodies = []
    rock_welds = []
    for i, (rx, ry) in enumerate(rock_xy):
        rz = 0.1 + terrain_height(rx, ry) + 0.6
        rock_bodies.append(
            f'<body name="rock{i}" pos="{rx:.3f} {ry:.3f} {rz:.3f}">'
            f'<freejoint/><geom type="sphere" size="0.2" mass="6" rgba="0.55 0.55 0.6 1"/>'
            f'</body>'
        )
        rock_welds.append(f'<weld name="w_rock{i}" body1="rock{i}"/>')

    tree_xy = [(2.0, -2.0), (3.0, 1.5), (2.5, 3.0)]
    trees = []
    for i, (tx, ty) in enumerate(tree_xy):
        base = 0.1 + terrain_height(tx, ty)
        trees.append(
            f'<body name="tree{i}" pos="{tx:.3f} {ty:.3f} {base + 0.5:.3f}">'
            f'<geom type="box" size="0.08 0.08 0.5" rgba="0.35 0.2 0.1 1"/>'
            f'<geom type="sphere" size="0.4" pos="0 0 0.75" rgba="0.1 0.45 0.15 1"/>'
            f'</body>'
        )

    vx, vy = 2.5, 0.0
    vz = 0.1 + terrain_height(vx, vy) + 0.28

    xml = f"""
<mujoco model="outdoor_rescue">
  <compiler angle="degree"/>
  <statistic center="0 0 0.6" extent="10"/>
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <asset>
    <hfield name="terrain" nrow="{n}" ncol="{n}" size="10 10 1 0.1">
{hfield_txt}
    </hfield>
  </asset>
  <worldbody>
    <geom name="ground" type="hfield" hfield="terrain"/>
    <geom name="victim" type="box" size="0.25 2.5 0.25" pos="{vx:.3f} {vy:.3f} {vz:.3f}" rgba="0.9 0.2 0.2 1"/>
    {''.join(trees)}
    {''.join(rock_bodies)}
  </worldbody>
  <equality>
    {''.join(rock_welds)}
  </equality>
</mujoco>
"""
    return xml


def run(headless=False):
    xml = build_xml()
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)

    rock_geom_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"rock{i}")
        for i in range(4)
    ]
    weld_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_EQUALITY, f"w_rock{i}")
        for i in range(4)
    ]
    victim_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "victim")
    victim_xy = np.array([2.5, 0.0])

    t1, t2 = 3.0, 6.0
    phase1 = False
    phase2 = False
    hit = False

    def check_hit():
        nonlocal hit
        if hit:
            return
        for i in range(4):
            body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"rock{i}")
            adr = model.jnt_qposadr[model.body_jntadr[body_id]]
            pos = data.qpos[adr:adr + 3]
            if np.linalg.norm(pos[:2] - victim_xy) < 0.6 and pos[2] < 1.0:
                hit = True
                print(f"[t={data.time:.2f}s] 滚石砸到受灾目标！")
                return

    def trigger_phase1():
        nonlocal phase1
        data.eq_active[weld_ids[0]] = 0
        data.eq_active[weld_ids[1]] = 0
        for i in (0, 1):
            body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"rock{i}")
            adr = model.jnt_dofadr[model.body_jntadr[body_id]]
            data.qvel[adr:adr + 3] = [2.5, 0.0, 0.0]
        phase1 = True
        print(f"[t={data.time:.2f}s] 第一次损毁：坡上两块滚石滑落")

    def trigger_phase2():
        nonlocal phase2
        data.eq_active[weld_ids[2]] = 0
        data.eq_active[weld_ids[3]] = 0
        for i in (2, 3):
            body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"rock{i}")
            adr = model.jnt_dofadr[model.body_jntadr[body_id]]
            data.qvel[adr:adr + 3] = [2.5, 0.0, 0.0]
        phase2 = True
        print(f"[t={data.time:.2f}s] 二次损毁：另两块滚石滑落")

    def step():
        mujoco.mj_step(model, data)

    if headless:
        for _ in range(int(10.0 / model.opt.timestep)):
            now = data.time
            if not phase1 and now >= t1:
                trigger_phase1()
            if not phase2 and now >= t2:
                trigger_phase2()
            step()
            check_hit()
        print("headless test done")
        return

    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running():
            now = data.time
            if not phase1 and now >= t1:
                trigger_phase1()
            if not phase2 and now >= t2:
                trigger_phase2()
            step()
            check_hit()
            viewer.sync()


if __name__ == "__main__":
    run(headless="--headless" in sys.argv)
