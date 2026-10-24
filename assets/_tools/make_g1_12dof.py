r"""从 g1_scene.xml（29 自由度）裁出 12 自由度腿版，供宇树官方 motion.pt 使用。

    python make_g1_12dof.py

做法：把腰 3 个 + 双臂 14 个关节**删掉**（对应身体就焊死在躯干上，视觉不变），
只留 12 个腿关节；执行器从 `<position>` 换成 `<motor>`（力矩），
因为官方 deploy 是 `tau = kp*(target-q) + kd*(0-dq)` 自己算力矩再 `d.ctrl = tau`。
另外补回 freejoint（官方用 `d.qpos[7:]` 取关节角）。

产物：assets/props/robots/g1/g1_12dof_scene.xml（nq=19 / nu=12）
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)
SRC = os.path.join(ASSETS, "props", "robots", "g1", "g1_scene.xml")
DST = os.path.join(ASSETS, "props", "robots", "g1", "g1_12dof_scene.xml")

LEG = ("left_hip_pitch", "left_hip_roll", "left_hip_yaw", "left_knee",
       "left_ankle_pitch", "left_ankle_roll",
       "right_hip_pitch", "right_hip_roll", "right_hip_yaw", "right_knee",
       "right_ankle_pitch", "right_ankle_roll")
DROP = ("waist_", "left_shoulder_", "left_elbow_", "left_wrist_",
        "right_shoulder_", "right_elbow_", "right_wrist_")


def _drop_bodies(xml, name_prefixes):
    """删掉名字以这些前缀开头的 <body> 子树（含嵌套），用于去掉双臂/腰。"""
    out, i, n = [], 0, len(xml)
    removed = 0
    while i < n:
        m = re.search(r"<body\s+[^>]*name=\"([^\"]+)\"[^>]*>", xml[i:])
        if not m:
            out.append(xml[i:])
            break
        start = i + m.start()
        name = m.group(1)
        out.append(xml[i:start])
        # 从 start 起做标签配对，找到对应的 </body>
        depth, j = 0, start
        while j < n:
            nxt_open = re.search(r"<body\s", xml[j:])
            nxt_close = re.search(r"</body>", xml[j:])
            if not nxt_close:
                j = n
                break
            if nxt_open and nxt_open.start() < nxt_close.start():
                depth += 1
                j += nxt_open.start() + 5
            else:
                depth -= 1
                j += nxt_close.start() + 7
                if depth == 0:
                    break
        block = xml[start:j]
        if any(name.startswith(p) for p in name_prefixes):
            removed += 1
        else:
            out.append(block)
        i = j
    return "".join(out), removed


def main():
    s = open(SRC, encoding="utf-8").read()

    # 1) 收集关节范围（做 ctrlrange）
    rng = {}
    for name, attrs in re.findall(r'<joint name="([^"]+)"([^>]*)>', s):
        m = re.search(r'range="([-\d.eE]+) ([-\d.eE]+)"', attrs)
        if m:
            rng[name] = (float(m.group(1)), float(m.group(2)))

    # 2) 删掉腰/臂关节
    pat = r'<joint name="(' + "|".join(DROP) + r')[^"]*"[^>]*/>'
    n_drop = len(re.findall(pat, s))
    s = re.sub(pat, "", s)

    # 2b) 把双臂/腰的 body 也整块删掉：官方 12 自由度模型没有手臂，
    #     留着焊死的胳膊会改质心/惯量，策略是在无手臂的模型上训的
    s, n_body = _drop_bodies(s, ("left_shoulder", "left_elbow", "left_wrist",
                                 "right_shoulder", "right_elbow", "right_wrist",
                                 "waist"))
    print(f"删掉 {n_body} 个手臂/腰 body")

    # 3) 执行器：position → motor（力矩）
    body = []
    for j in LEG:
        jn = j + "_joint"
        lo, hi = rng.get(jn, (-200.0, 200.0))
        body.append(f'    <motor name="{j}_motor" joint="{jn}" '
                    f'ctrlrange="{lo:g} {hi:g}"/>')
    new_act = "  <actuator>\n" + "\n".join(body) + "\n  </actuator>"
    s, n_act = re.subn(r"<actuator>.*?</actuator>", new_act, s, flags=re.S)

    # 4) 补回 freejoint（g1_scene 是固定基座版，被我们删过）
    added_free = False
    if "freejoint" not in s:
        s = re.sub(r'(<body name="pelvis"[^>]*>)',
                   r'\1\n      <freejoint name="floating_base_joint"/>', s, count=1)
        added_free = True

    open(DST, "w", encoding="utf-8").write(s)
    print(f"删掉 {n_drop} 个非腿关节，替换 {n_act} 个 actuator 段，补 freejoint={added_free}")
    print(f"wrote {os.path.relpath(DST, ASSETS)} ({os.path.getsize(DST)/1024:.1f} KB)")

    import mujoco
    m = mujoco.MjModel.from_xml_path(DST)
    print(f"校验：nq={m.nq} nu={m.nu}（应为 19 / 12）body={m.nbody} geom={m.ngeom}")
    names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, i) for i in range(m.nu)]
    print("  执行器:", names)


if __name__ == "__main__":
    main()
