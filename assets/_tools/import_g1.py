r"""把宇树 G1 人形机器人导进 MuJoCo（官方 g1_description/g1_29dof.xml + STL 网格）。

    python import_g1.py              # 缺什么下什么，然后生成两个场景
    python import_g1.py --check      # 只报清单

产物（assets/props/robots/g1/）：
    g1_scene.xml   基座固定在世界的版本（摆场景/当 NPC 用，绝不会倒）
    g1_free.xml    带 freejoint 的版本（可以做物理/RL，但没有控制器会摔）
"""
import argparse
import os
import re
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
OUT = os.path.join(ASSETS, "props", "robots", "g1")
BASE = ("https://raw.githubusercontent.com/unitreerobotics/unitree_ros/master/"
        "robots/g1_description")
VARIANT = "g1_29dof"
MIRROR = "https://ghfast.top/"          # 本机直连 raw 经常被 reset，走镜像兜底


def _one(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "dsh-fetch"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get(url, binary=True, tries=5):
    """直连失败就换镜像，再失败就退避重试（这台机器经常 WinError 10054）。"""
    last = None
    urls = [url, MIRROR + url]
    for attempt in range(tries):
        for u in urls:
            try:
                b = _one(u)
                if b:
                    return b if binary else b.decode("utf-8")
            except Exception as e:          # noqa: BLE001
                last = e
        time.sleep(1.0 + attempt)
    raise RuntimeError(f"下载失败：{url} ({last})")


def fetch():
    from concurrent.futures import ThreadPoolExecutor

    os.makedirs(os.path.join(OUT, "meshes"), exist_ok=True)
    xp = os.path.join(OUT, f"{VARIANT}.xml")
    if not os.path.exists(xp):
        xml = get(f"{BASE}/{VARIANT}.xml", binary=False)
        open(xp, "w", encoding="utf-8").write(xml)
        print(f"  {VARIANT}.xml  {len(xml)/1024:.1f} KB")
    xml = open(xp, encoding="utf-8").read()
    meshes = sorted(set(re.findall(r'file="([^"]+\.STL)"', xml, re.I)))
    todo = [m for m in meshes if not (os.path.exists(os.path.join(OUT, "meshes", m))
                                      and os.path.getsize(os.path.join(OUT, "meshes", m)) > 0)]
    print(f"  网格 {len(meshes)} 个，其中待下载 {len(todo)} 个")

    def one(m):
        b = get(f"{BASE}/meshes/{m}")
        p = os.path.join(OUT, "meshes", m)
        open(p, "wb").write(b)
        return len(b)

    if todo:
        with ThreadPoolExecutor(max_workers=8) as ex:
            sizes = list(ex.map(one, todo))
        print(f"  本次下载 {sum(sizes)/1e6:.1f} MB")
    total = sum(os.path.getsize(os.path.join(OUT, "meshes", m)) for m in meshes)
    print(f"  网格合计 {total/1e6:.1f} MB")
    return xml


def build(xml):
    import mujoco

    # 1) 视觉/离屏缓冲
    if "offwidth" not in xml:
        xml = re.sub(r"(<mujoco[^>]*>)",
                     r'\1\n  <visual><global offwidth="1280" offheight="720"/>'
                     r'<headlight ambient="0.4 0.4 0.42" diffuse="0.6 0.6 0.6" '
                     r'specular="0.1 0.1 0.1"/></visual>', xml, count=1)

    # 2) motor(力矩) -> position(位置)：固定基座下能稳稳保持姿态
    def to_pos(m):
        name, joint = m.group(1), m.group(2)
        rng = re.search(rf'<joint name="{joint}"[^>]*range="([-\d.]+) ([-\d.]+)"', xml)
        lo, hi = (rng.group(1), rng.group(2)) if rng else ("-1.5", "1.5")
        eff = re.search(rf'<joint name="{joint}"[^>]*effort="([\d.]+)"', xml)
        f = float(eff.group(1)) if eff else 50.0
        return (f'    <position name="{name}" joint="{joint}" kp="150" dampratio="1" '
                f'ctrlrange="{lo} {hi}" forcerange="{-f:.1f} {f:.1f}"/>')
    xml = re.sub(r'    <motor name="([^"]+)" joint="([^"]+)"/>', to_pos, xml)

    # 3) 地面 + 光 + 相机 + 时间步
    if "<option" not in xml:
        xml = re.sub(r"(<mujoco[^>]*>)",
                     r'\1\n  <option timestep="0.002" integrator="implicitfast"/>', xml, count=1)
    ground = ('<geom name="floor" type="plane" size="4 4 0.05" rgba="0.35 0.38 0.32 1"/>\n'
              '    <light pos="1.2 1.2 2.4" dir="-0.4 -0.4 -1" diffuse="0.7 0.7 0.7"/>\n'
              '    <camera name="track" pos="1.6 -1.6 1.3" xyaxes="0.707 0.707 0 -0.3 0.3 0.9"/>\n    ')
    if 'name="floor"' not in xml:
        xml = re.sub(r"(<worldbody>)", r"\1\n    " + ground, xml, count=1)
    return xml


def no_free(xml):
    """官方 G1 的 pelvis 自带 `<joint type="free">`（浮动基座）。
    去掉它 → 基座焊进世界坐标系，摆场景时绝不会倒。"""
    out, n = re.subn(r'\s*<joint name="floating_base_joint"[^>]*/>', "", xml, count=1)
    print(f"  去掉浮动基座关节 {n} 处（fixed 版本）")
    return out


def seat(xml):
    """让脚底正好落在 z=0：算出当前最低点，把 pelvis 抬上去。"""
    import mujoco

    # 注意：from_xml_string 解析不了相对 meshdir，必须落盘再 from_xml_path
    probe_xml = xml
    probe_path = os.path.join(OUT, "_probe.xml")
    open(probe_path, "w", encoding="utf-8").write(probe_xml)
    try:
        m = mujoco.MjModel.from_xml_path(probe_path)
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        # 不能拿 geom_rbound 当"脚底"：网格的 rbound 是包围球半径，会高估一截
        lows = []
        for g in range(m.ngeom):
            z0 = float(d.geom_xpos[g][2])
            if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH and m.geom_dataid[g] >= 0:
                di = m.geom_dataid[g]
                v0, nv = m.mesh_vertadr[di], m.mesh_vertnum[di]
                sc = float(m.mesh_scale[di][2])
                lows.append(z0 + float(m.mesh_vert[v0:v0 + nv][:, 2].min()) * sc)
            else:
                lows.append(z0 - float(m.geom_size[g][2]))
        dz = -min(lows)
    finally:
        if os.path.exists(probe_path):
            os.remove(probe_path)

    tag = '<body name="pelvis"'
    if re.search(tag + r'[^>]*pos="', xml):
        xml = re.sub(rf'({tag}[^>]*?pos="[-\d.]+ [-\d.]+ )([-\d.]+)(")',
                     lambda mm: mm.group(1) + f"{float(mm.group(2)) + dz:.3f}" + mm.group(3),
                     xml, count=1)
    else:
        xml = re.sub(rf'({tag})', rf'\1 pos="0 0 {dz:.3f}"', xml, count=1)
    return xml, dz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    print(f"[1/3] 下载 {VARIANT}")
    xml = fetch()
    if args.check:
        return

    print("[2/3] 改造：位置电机 + 地面光照相机 + 贴地")
    xml = build(xml)
    fixed, dz = seat(no_free(xml))
    free = xml

    p_fixed = os.path.join(OUT, "g1_scene.xml")
    p_free = os.path.join(OUT, "g1_free.xml")
    open(p_fixed, "w", encoding="utf-8").write(fixed)
    open(p_free, "w", encoding="utf-8").write(free)

    print("[3/3] 验证")
    import mujoco
    for path, is_free in ((p_fixed, False), (p_free, True)):
        m = mujoco.MjModel.from_xml_path(path)
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        pel = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
        z0 = float(d.xpos[pel][2])
        for _ in range(1000):                     # 2 s
            mujoco.mj_step(m, d)
        z1 = float(d.xpos[pel][2])
        name = os.path.basename(path)
        print(f"  {name:<14} nq={m.nq:>2} nu={m.nu:>2} mass={m.body_mass.sum():5.1f} kg  "
              f"骨盆 z {z0:.3f} -> {z1:.3f} m")


if __name__ == "__main__":
    main()
