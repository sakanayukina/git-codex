r"""把 unitree_ros 的 Go2 URDF 变成 MuJoCo 能直接加载的版本。

    python import_go2_urdf.py

做三件事：
1. 把 meshes/*.dae 全转成 OBJ（MuJoCo 不认 DAE）
2. 把 URDF 里的 package:// 路径改成本地相对路径
3. 注入 `<mujoco>` 块：保留 visual、给 base 加 freejoint（否则狗被焊死在地上）

产物：assets/props/robots/go2_urdf/go2_mujoco.urdf
"""
import argparse
import os
import re
import xml.etree.ElementTree as ET

import dae2obj

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
ROOT = os.path.join(ASSETS, "props", "robots", "go2_urdf")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=ROOT)
    args = ap.parse_args()

    mdir = os.path.join(args.dir, "meshes")
    daes = sorted(f for f in os.listdir(mdir) if f.endswith(".dae"))
    print(f"COLLADA -> OBJ: {len(daes)} 个")
    total = 0
    for f in daes:
        src = os.path.join(mdir, f)
        dst = os.path.join(mdir, f[:-4] + ".obj")
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            print(f"  {f[:-4]+'.obj':<22} 已存在，跳过")
            continue
        V, F = dae2obj.convert(src, dst)
        total += len(F)
        lo, hi = V.min(0), V.max(0)
        print(f"  {f[:-4]+'.obj':<22} {len(F):7d} tris  "
              f"{hi[0]-lo[0]:.3f} x {hi[1]-lo[1]:.3f} x {hi[2]-lo[2]:.3f} m")
    print(f"新增合计 {total} tris")

    # ---- 改写 URDF
    src = os.path.join(args.dir, "go2_description.urdf")
    dst = os.path.join(args.dir, "go2_mujoco.urdf")
    xml = open(src, encoding="utf-8").read()

    def fix_mesh(m):
        name = os.path.basename(m.group(1))
        return f'<mesh filename="meshes/{os.path.splitext(name)[0]}.obj"'
    xml, n = re.subn(r'<mesh filename="([^"]+\.dae)"', fix_mesh, xml)
    print(f"mesh 路径改写: {n} 处")

    # unitree 的 URDF 在一个 <visual> 里塞了 5 个 <material>（URDF 规范不允许），
    # MuJoCo 会报 "repeated element: 'material'" → 每个 visual 只留第一个
    def one_material(m):
        block = m.group(1)
        found = []

        def keep(mm):
            found.append(1)
            return mm.group(0) if len(found) == 1 else ""
        block = re.sub(r"<material\b[^>]*>.*?</material>|<material\b[^>]*/>", keep, block, flags=re.S)
        return f"<visual>{block}</visual>"
    xml = re.sub(r"<visual>(.*?)</visual>", one_material, xml, flags=re.S)
    print("每个 visual 只保留第一个 material")

    # MuJoCo 的 URDF 扩展：保留 visual、不要合并 static 子节点
    mujoco_robot = ('<mujoco><compiler discardvisual="false" strippath="false" '
                    'fusestatic="false"/></mujoco>')
    if "<mujoco>" not in xml:
        xml = re.sub(r'(<robot[^>]*>)', r'\1\n' + mujoco_robot, xml, count=1)

    open(dst, "w", encoding="utf-8").write(xml)
    ET.parse(dst)
    print(f"wrote {os.path.relpath(dst, ASSETS)} ({os.path.getsize(dst)/1024:.1f} KB)")

    # ---- 关键：MuJoCo 3.3.2 的 URDF 解析器**忽略** <link> 里的 <mujoco><joint type=free>，
    #      所以 base 会焊死在 worldbody 上（nq 只有 12）。办法是先用 URDF 编译一遍，
    #      导出成 MJCF，再在 MJCF 里加 freejoint / 电机 / 地面。
    import mujoco
    os.chdir(args.dir)
    m = mujoco.MjModel.from_xml_path("go2_mujoco.urdf")
    mujoco.mj_saveLastXML("go2_from_urdf.xml", m)
    print(f"URDF -> MJCF: {m.nbody} body / {m.ngeom} geom / nq={m.nq}")

    mj = open("go2_from_urdf.xml", encoding="utf-8").read()

    # 1) base 加浮动关节
    if "<freejoint" not in mj:
        mj = re.sub(r'(<body name="base"[^>]*>)',
                    r'\1\n      <freejoint name="floating_base"/>', mj, count=1)

    # 2) 12 个位置电机：kp 取 20，力矩上限用 URDF 的 effort
    joints = []
    for mo in re.finditer(r'<joint name="([^"]+)" type="revolute">(.*?)</joint>', xml, re.S):
        name, body = mo.group(1), mo.group(2)
        effort = re.search(r'<limit[^>]*effort="([\d.eE+-]+)"', body)
        lo = re.search(r'<limit[^>]*lower="([\d.eE+-]+)"', body)
        hi = re.search(r'<limit[^>]*upper="([\d.eE+-]+)"', body)
        joints.append((name, float(effort.group(1)) if effort else 23.7,
                       float(lo.group(1)) if lo else -1.0,
                       float(hi.group(1)) if hi else 1.0))
    if joints and "<actuator>" not in mj:
        acts = "".join(
            f'    <position name="{n}_pos" joint="{n}" kp="100" '
            f'ctrlrange="{lo:.3f} {hi:.3f}" forcerange="{-eff:.3f} {eff:.3f}"/>\n'
            for n, eff, lo, hi in joints)
        mj = mj.replace("</mujoco>", f"  <actuator>\n{acts}  </actuator>\n</mujoco>")
        print(f"加了 {len(joints)} 个位置电机（kp=100）")

    # 3) 时间步 + 地面/光照/相机（做成可直接跑的独立场景）
    mj = re.sub(r"<option[^>]*/>", "", mj)
    mj = mj.replace("<mujoco", '<mujoco', 1)
    if "<option" not in mj:
        mj = re.sub(r"(<mujoco[^>]*>)", r'\1\n  <option timestep="0.002" integrator="implicitfast"/>', mj, count=1)
    # 离屏渲染缓冲：默认 640x480，放大后 renderer 才能出图
    if "offwidth" not in mj:
        mj = re.sub(r"(<mujoco[^>]*>)",
                    r'\1\n  <visual><global offwidth="1280" offheight="720"/>'
                    r'<headlight ambient="0.38 0.38 0.42" diffuse="0.6 0.6 0.6" '
                    r'specular="0.1 0.1 0.1"/></visual>', mj, count=1)
    ground = ('<geom name="floor" type="plane" size="4 4 0.05" rgba="0.35 0.38 0.32 1"/>\n'
              '    <light pos="1 1 3" dir="-0.3 -0.3 -1" diffuse="0.65 0.65 0.65"/>\n'
              '    <camera name="track" pos="1.1 -1.1 0.75" xyaxes="0.707 0.707 0 -0.35 0.35 0.87"/>\n    ')
    if 'name="floor"' not in mj:
        mj = re.sub(r"(<worldbody>)", r"\1\n    " + ground, mj, count=1)

    scene = os.path.join(args.dir, "go2_scene.xml")
    open(scene, "w", encoding="utf-8").write(mj)
    mj_ok = mujoco.MjModel.from_xml_path("go2_scene.xml")
    print(f"wrote go2_scene.xml: nq={mj_ok.nq} nv={mj_ok.nv} nu={mj_ok.nu} "
          f"mass={mj_ok.body_mass.sum():.2f} kg")

    # ---- 站立姿态：URDF 的零位是"腿伸直"，狗站不住。
    #      用 menagerie 的 home 姿态（大腿 0.9 rad、小腿 -1.8 rad、机身 0.27 m）。
    STAND = {"hip": 0.0, "thigh": 0.9, "calf": -1.8}
    qpos_angles, ctrl_angles = [], []
    for i in range(mj_ok.njnt):
        jn = mujoco.mj_id2name(mj_ok, mujoco.mjtObj.mjOBJ_JOINT, i)
        if mj_ok.jnt_type[i] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        key = "hip" if "hip" in jn else ("calf" if "calf" in jn else "thigh")
        qpos_angles.append(STAND[key])
    for i in range(mj_ok.nu):
        an = mujoco.mj_id2name(mj_ok, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
        jn = an.replace("_pos", "")
        key = "hip" if "hip" in jn else ("calf" if "calf" in jn else "thigh")
        ctrl_angles.append(STAND[key])

    mj = open("go2_scene.xml", encoding="utf-8").read()
    mj = re.sub(r'(<body name="base")', r'\1 pos="0 0 0.27"', mj, count=1)
    qpos = "0 0 0.27 1 0 0 0 " + " ".join(f"{a:.3f}" for a in qpos_angles)
    ctrl = " ".join(f"{a:.3f}" for a in ctrl_angles)
    if "<keyframe>" not in mj:
        mj = mj.replace("</mujoco>",
                        f'  <keyframe>\n    <key name="home" qpos="{qpos}" ctrl="{ctrl}"/>\n'
                        f"  </keyframe>\n</mujoco>")
    open("go2_scene.xml", "w", encoding="utf-8").write(mj)

    m2 = mujoco.MjModel.from_xml_path("go2_scene.xml")
    d2 = mujoco.MjData(m2)
    mujoco.mj_resetDataKeyframe(m2, d2, 0)
    for _ in range(1000):                     # 2 s @ 2 ms
        mujoco.mj_step(m2, d2)
    bid = mujoco.mj_name2id(m2, mujoco.mjtObj.mjOBJ_BODY, "base")
    print(f"站立测试：2 秒后 base z = {d2.xpos[bid][2]:.3f} m（目标 ~0.27）")


if __name__ == "__main__":
    main()
