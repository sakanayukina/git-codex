"""把 `assets/terrain/hf_road.npz`（float 高度场）注入模型。

为什么需要：MuJoCo 的 hfield 只能从 8-bit PNG 读，256 级 = 0.26 m 量化，
做不出平滑路面。所以 PNG 只负责确定 nrow/ncol，真正的路面高程在模型加载后
用 `model.hfield_data[:] = data` 覆盖（3.3.2 实测：物理 ray-cast 与渲染都会跟着变，
没有 `mj_setHeightFieldData` 也能用）。

用法：
    from terrain_road import load_model
    m = load_model("assets/village_duo.xml")     # 自动注入
    m = load_model(xml, inject=False)            # 保留 8-bit 地形（对照用）

    python terrain_road.py --verify              # 校验：PNG vs npz 的高度差、路面坡度
"""
import argparse
import os

import mujoco
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.normpath(os.path.join(BASE, ".."))
NPZ = os.path.join(ASSETS, "terrain", "hf_road.npz")


def read_npz(path=NPZ):
    if not os.path.exists(path):
        return None
    z = np.load(path)
    return dict(data=np.asarray(z["data"], dtype=np.float32),
                nrow=int(z["nrow"]), ncol=int(z["ncol"]),
                elev=float(z["elev"]), base=float(z["base"]),
                radius=float(z["radius"]), cell=float(z["cell"]))


def apply(model, path=NPZ, verbose=False):
    """把 float 高度场写进 model.hfield_data（尺寸不符时跳过并告警）。"""
    hf = read_npz(path)
    if hf is None:
        return False
    geoms = np.flatnonzero(model.geom_type == mujoco.mjtGeom.mjGEOM_HFIELD)
    if len(geoms) == 0:
        return False
    hid = int(model.geom_dataid[int(geoms[0])])
    nr, nc = int(model.hfield_nrow[hid]), int(model.hfield_ncol[hid])
    if (nr, nc) != (hf["nrow"], hf["ncol"]):
        if verbose:
            print("[terrain_road] skip: scene hfield %dx%d != npz %dx%d "
                  "(把场景 hfield 指到 terrain/height_field_road.png)"
                  % (nr, nc, hf["nrow"], hf["ncol"]))
        return False
    model.hfield_data[:] = hf["data"].ravel()
    if verbose:
        print("[terrain_road] injected %.0f k cells (%.3f m/cell)"
              % (hf["data"].size / 1000.0, hf["cell"]))
    return True


def load_model(xml, inject=True, path=NPZ, verbose=False):
    m = mujoco.MjModel.from_xml_path(xml)
    if inject:
        apply(m, path=path, verbose=verbose)
    return m


def ray_height(model, data, x, y, z0=400.0):
    """只认 hfield 的命中（房子/道具会挡住射线，给错高度）。"""
    hid = int(model.geom_dataid[int(np.flatnonzero(
        model.geom_type == mujoco.mjtGeom.mjGEOM_HFIELD)[0])])
    gid = np.zeros(1, dtype=np.int32)
    dist = mujoco.mj_ray(model, data, np.array([x, y, z0]), np.array([0.0, 0.0, -1.0]),
                         None, 1, -1, gid)
    if dist <= 0 or int(gid[0]) != hid:
        return np.nan
    return z0 - dist


def plane_normal(model, data, x, y, radius=1.5):
    """用机器人周围四个轴向 hfield 采样点算地形法向（世界系，向上单位向量）。

    采样半径默认 1.5 m，比 G1 站立占地大得多，不会命中机器人自身几何。
    只用中心差分，**不调用 numpy.linalg.lstsq**：本机在 mujoco+torch 一起加载后
    lstsq 会触发 Windows fatal exception 0xc06d007f（LAPACK 延迟加载失败）。
    """
    for r in (radius, radius * 1.7, 0.9, 2.6):
        hx1 = ray_height(model, data, x + r, y)
        hx0 = ray_height(model, data, x - r, y)
        hy1 = ray_height(model, data, x, y + r)
        hy0 = ray_height(model, data, x, y - r)
        if not (np.isfinite(hx1) and np.isfinite(hx0) and np.isfinite(hy1) and np.isfinite(hy0)):
            continue
        gx = (hx1 - hx0) / (2.0 * r)
        gy = (hy1 - hy0) / (2.0 * r)
        n = np.array([-gx, -gy, 1.0])
        return n / np.linalg.norm(n)
    return np.array([0.0, 0.0, 1.0])


def _roads():
    import json
    cfg = json.load(open(os.path.join(ASSETS, "buildings.json"), encoding="utf-8"))
    import carve_roads
    return carve_roads.build_roads(cfg)


def verify(scene=None, step=0.5):
    scene = scene or os.path.join(ASSETS, "village_duo.xml")
    hf = read_npz()

    m0 = mujoco.MjModel.from_xml_path(scene)
    d0 = mujoco.MjData(m0)
    mujoco.mj_forward(m0, d0)
    m1 = load_model(scene)
    d1 = mujoco.MjData(m1)
    mujoco.mj_forward(m1, d1)
    assert m1.hfield_data.max() != 0 or hf is None

    print("hfield %dx%d, npz %s" % (m0.hfield_nrow[0], m0.hfield_ncol[0],
                                    "ok" if hf else "missing"))

    # 1) 方向校验：PNG（8-bit）与 npz（float）在同一点的高度差
    rng = np.random.default_rng(0)
    pts = rng.uniform(-95, 95, size=(400, 2))
    diffs = []
    for x, y in pts:
        a = ray_height(m0, d0, x, y)
        b = ray_height(m1, d1, x, y)
        if np.isfinite(a) and np.isfinite(b):
            diffs.append(abs(a - b))
    diffs = np.array(diffs)
    print("PNG vs npz height: mean %.3f m, p95 %.3f m, max %.3f m  (0.26 m 量化以内即方向正确)"
          % (diffs.mean(), np.percentile(diffs, 95), diffs.max()))

    # 2) 每条路的纵坡（沿中心线，用 npz 注入后的物理表面量）
    print("\n%-10s %7s %8s %8s %8s %8s" % ("road", "len(m)", "grade_mean", "grade_p95",
                                           "grade_max", "dz_span"))
    for poly, width, name in _roads():
        import carve_roads
        x, y, s = carve_roads.resample(poly, step)
        z = np.array([ray_height(m1, d1, xi, yi) for xi, yi in zip(x, y)])
        ok = np.isfinite(z)
        z = z[ok]
        if len(z) < 3:
            continue
        ds = step
        g = np.degrees(np.arctan(np.abs(np.diff(z)) / ds))
        print("%-10s %7.1f %8.2f %8.2f %8.2f %8.2f"
              % (name, float(s[-1]), g.mean(), np.percentile(g, 95), g.max(), z.max() - z.min()))

    # 3) 横断面：主路中心两侧 ±1.5 m 的高度差（应接近 0）
    import carve_roads
    poly, width, _ = _roads()[0]
    x, y, s = carve_roads.resample(poly, 2.0)
    dy = np.gradient(y)
    dx = np.gradient(x)
    nrm = np.hypot(dx, dy)
    nx, ny = -dy / nrm, dx / nrm
    cross = []
    for k in range(len(x)):
        zs = [ray_height(m1, d1, x[k] + nx[k] * o, y[k] + ny[k] * o) for o in (-1.5, 0.0, 1.5)]
        if all(np.isfinite(zs)):
            cross.append(max(zs) - min(zs))
    cross = np.array(cross)
    print("\ncross-slope of main road (|dz| over 3 m width): mean %.3f m, max %.3f m"
          % (cross.mean(), cross.max()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--scene", default=None)
    args = ap.parse_args()
    if args.verify:
        verify(args.scene)
    else:
        print("usage: python terrain_road.py --verify")
