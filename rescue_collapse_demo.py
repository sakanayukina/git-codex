import sys

import mujoco
import mujoco.viewer
import numpy as np


XML = r"""
<mujoco model="rescue_collapse">
  <compiler angle="degree"/>
  <statistic center="0 0 1" extent="3"/>
  <option timestep="0.002" gravity="0 0 -9.81"/>

  <worldbody>
    <geom name="floor" type="plane" size="6 6 0.1" rgba="0.3 0.3 0.3 1"/>

    <body name="roof" pos="0 0 1.24">
      <freejoint/>
      <geom name="roof_geom" type="box" size="1.4 1.4 0.04" mass="80" rgba="0.65 0.55 0.45 1"/>
    </body>

    <body name="pillar1" pos="-0.8 0 0.6">
      <freejoint/>
      <geom name="pillar1_geom" type="box" size="0.07 0.07 0.6" mass="10" rgba="0.5 0.5 0.5 1"/>
    </body>

    <body name="pillar2" pos="0.8 0 0.6">
      <freejoint/>
      <geom name="pillar2_geom" type="box" size="0.07 0.07 0.6" mass="10" rgba="0.5 0.5 0.5 1"/>
    </body>

    <body name="victim" pos="0.6 0 0.4">
      <freejoint/>
      <geom name="victim_geom" type="capsule" size="0.12 0.25" mass="70" rgba="0.9 0.2 0.2 1"/>
    </body>
  </worldbody>

  <equality>
    <weld name="w_p1" body1="pillar1"/>
    <weld name="w_p2" body1="pillar2"/>
    <weld name="w_victim" body1="victim"/>
  </equality>
</mujoco>
"""


def run(headless=False):
    model = mujoco.MjModel.from_xml_string(XML)
    data = mujoco.MjData(model)

    w_p1 = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_EQUALITY, "w_p1")
    w_p2 = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_EQUALITY, "w_p2")
    roof_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "roof")
    victim_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "victim")

    t1, t2 = 2.0, 4.0
    collapsed1 = False
    collapsed2 = False
    hit = False

    def move_away(body_name):
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
        jnt = model.body_jntadr[body_id]
        adr = model.jnt_qposadr[jnt]
        data.qpos[adr:adr + 3] = [10.0, 10.0, 5.0]

    def report_contacts(tag):
        nonlocal hit
        if hit:
            return
        for c in data.contact:
            b1 = model.geom_bodyid[c.geom1]
            b2 = model.geom_bodyid[c.geom2]
            if {b1, b2} == {roof_body, victim_body}:
                hit = True
                print(f"[t={data.time:.2f}s] {tag} 顶板压到被困者！")
                return

    def step():
        mujoco.mj_step(model, data)

    if headless:
        for _ in range(int(8.0 / model.opt.timestep)):
            now = data.time
            if not collapsed1 and now >= t1:
                data.eq_active[w_p1] = 0
                move_away("pillar1")
                collapsed1 = True
                print(f"[t={now:.2f}s] 第一次坍塌：移除左侧支柱")
            if not collapsed2 and now >= t2:
                data.eq_active[w_p2] = 0
                move_away("pillar2")
                collapsed2 = True
                print(f"[t={now:.2f}s] 二次坍塌：移除右侧支柱")
            step()
            report_contacts("")
        print("headless test done")
        print("roof final z =", round(float(data.qpos[2]), 3))
        return

    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running():
            now = data.time
            if not collapsed1 and now >= t1:
                data.eq_active[w_p1] = 0
                move_away("pillar1")
                collapsed1 = True
                print(f"[t={now:.2f}s] 第一次坍塌：移除左侧支柱")
            if not collapsed2 and now >= t2:
                data.eq_active[w_p2] = 0
                move_away("pillar2")
                collapsed2 = True
                print(f"[t={now:.2f}s] 二次坍塌：移除右侧支柱")
            step()
            report_contacts("")
            viewer.sync()


if __name__ == "__main__":
    run(headless="--headless" in sys.argv)
