"""S1：把村道修成真的能走的路——按 buildings.json 的主路 + 入户支路把地形走廊压平。

思路
  1. 从**原始**地形 `assets/terrain/height_field_patch.png`（8-bit 128x128）双线性重采样到
     细网格（默认 0.6 m/格）。
  2. 按 `assets/buildings.json` 复刻路网（主路 4.2 m + 7 条入户支路 3.0 m）。
  3. 把整个路网看成一张**图**：每条路沿中心线 0.25 m 采样成节点，支路首节点与主路最近节点
     连一条短边（路口）。于是"路口处两条路高度必须一致"变成图的连通约束，自动满足。
  4. 在图上先把节点高度平滑（拉普拉斯迭代），再做**限坡投影**（反复裁 |Δh| ≤ tan(g)*长度，
     默认 8 度），直到收敛 ⇒ 全路网处处 ≤8 度、路口无台阶、且只做局部削/填。
  5. 网格单元取最近路网节点的高度 ⇒ 走廊内**横断面水平**；走廊外 smoothstep 过渡带
     （默认 6 m）混回原地形，走廊外地形完全不动 —— 废墟、岩石、植被、坡地都保留。
  6. 输出 float 高度场 `assets/terrain/hf_road.npz`（物理/规划用那个：运行时注入
     `model.hfield_data`，因为 8-bit PNG 只有 256 级 = 0.26 m 量化，做不出平滑路面），
     另写 8-bit PNG `assets/terrain/height_field_road.png` 供确定网格尺寸与裸 viewer 预览。

用法
    python carve_roads.py                       # 生成 npz + png，打印统计
    python carve_roads.py --apply               # 顺便把场景的 hfield 指到新 PNG
    python carve_roads.py --max-grade 6 --band 8 --res 0.5
"""
import argparse
import json
import math
import os
import struct
import zlib

import mujoco
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.normpath(os.path.join(BASE, ".."))
CONFIG = os.path.join(ASSETS, "buildings.json")
BASE_PNG = "terrain/height_field_patch.png"
OUT_NPZ = os.path.join(ASSETS, "terrain", "hf_road.npz")
OUT_PNG = os.path.join(ASSETS, "terrain", "height_field_road.png")
SCENES_TO_PATCH = ["demo_v32.xml", "village_duo.xml", "village_duo_go2x2.xml",
                   "village_walk_final.xml", "g1_village_final.xml", "village_walk4_patch.xml"]


# ------------------------------------------------------------------ 原始地形
class BaseField:
    """原始 hfield 的双线性采样器（索引随 +y / +x 增大，已用 ray-cast 校验）。

    必须读原始 PNG：读场景里已经修过路的 hfield 会把路面再削一遍。
    """

    def __init__(self, png=BASE_PNG, size="100 100 66.5 0.01"):
        tmp = os.path.join(ASSETS, "_tmp_hf_base.xml")
        open(tmp, "w", encoding="utf-8").write(
            '<mujoco><asset><hfield name="h" file="%s" size="%s"/></asset>'
            '<worldbody><geom type="hfield" hfield="h"/></worldbody></mujoco>' % (png, size))
        try:
            m = mujoco.MjModel.from_xml_path(tmp)
        finally:
            os.remove(tmp)
        g = int(np.flatnonzero(m.geom_type == mujoco.mjtGeom.mjGEOM_HFIELD)[0])
        hf = int(m.geom_dataid[g])
        self.data = np.array(m.hfield_data.reshape(m.hfield_nrow[hf], m.hfield_ncol[hf]),
                             dtype=np.float64)
        self.nr, self.nc = self.data.shape
        self.radius = float(m.hfield_size[hf][0])
        self.elev = float(m.hfield_size[hf][2])
        self.base = float(m.hfield_size[hf][3])

    def __call__(self, x, y):
        u = (np.asarray(y, dtype=np.float64) + self.radius) / (2 * self.radius) * (self.nr - 1)
        v = (np.asarray(x, dtype=np.float64) + self.radius) / (2 * self.radius) * (self.nc - 1)
        u = np.clip(u, 0, self.nr - 1)
        v = np.clip(v, 0, self.nc - 1)
        i0 = np.floor(u).astype(int)
        j0 = np.floor(v).astype(int)
        i1 = np.minimum(i0 + 1, self.nr - 1)
        j1 = np.minimum(j0 + 1, self.nc - 1)
        du = u - i0
        dv = v - j0
        d = self.data
        z = (d[i0, j0] * (1 - du) * (1 - dv) + d[i1, j0] * du * (1 - dv)
             + d[i0, j1] * (1 - du) * dv + d[i1, j1] * du * dv)
        return self.base + z * self.elev


# ------------------------------------------------------------------ 路网
def build_roads(cfg):
    main_pts = [(float(a), float(b)) for a, b in cfg["road"]["points"]]
    roads = [(main_pts, float(cfg["road"]["width"]), "main")]

    def closest(px, py, pts):
        best, bd = None, 1e9
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy or 1e-6
            t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
            cx, cy = x0 + dx * t, y0 + dy * t
            d = math.hypot(px - cx, py - cy)
            if d < bd:
                best, bd = (cx, cy), d
        return best

    for p in cfg.get("plots", []):
        a = math.radians(p["yaw"])
        dx, dy = math.sin(a) * p["size"][1] / 2, -math.cos(a) * p["size"][1] / 2
        door = (p["x"] + dx, p["y"] + dy)
        tgt = closest(door[0], door[1], main_pts)
        if tgt is None or math.hypot(door[0] - tgt[0], door[1] - tgt[1]) < 1.0:
            continue
        mid = ((door[0] + tgt[0]) / 2.0, (door[1] + tgt[1]) / 2.0)
        roads.append(([tgt, mid, door], 3.0, "spur_%s" % p["id"]))
    return roads


def resample(poly, ds=0.25):
    pts = np.asarray(poly, dtype=np.float64)
    seg = np.diff(pts, axis=0)
    lens = np.hypot(seg[:, 0], seg[:, 1])
    total = float(lens.sum())
    n = max(2, int(round(total / ds)) + 1)
    s = np.linspace(0.0, total, n)
    cum = np.concatenate([[0.0], np.cumsum(lens)])
    return np.interp(s, cum, pts[:, 0]), np.interp(s, cum, pts[:, 1]), s


# ------------------------------------------------------------------ 图上的高度
class RoadGraph:
    def __init__(self, bf, roads, ds):
        self.road_of = []
        self.x, self.y, self.z, self.node_of = [], [], [], []
        edges = []
        cursor = 0
        for ri, (poly, width, name) in enumerate(roads):
            x, y, s = resample(poly, ds)
            z = bf(x, y)
            k = len(x)
            self.x.append(x)
            self.y.append(y)
            self.z.append(z)
            self.road_of.append(np.full(k, ri))
            for i in range(k - 1):
                edges.append((cursor + i, cursor + i + 1, float(s[i + 1] - s[i])))
            self.node_of.append(cursor)
            cursor += k
        self.ds = ds
        self.n = cursor
        self.x = np.concatenate(self.x)
        self.y = np.concatenate(self.y)
        self.z_raw = np.concatenate(self.z)
        self.road = np.concatenate(self.road_of)
        self.node_of = np.asarray(self.node_of)

        # 路口：每条支路的首节点连到主路最近节点
        main_x, main_y = self.x[self.road == 0], self.y[self.road == 0]
        main_ids = np.flatnonzero(self.road == 0)
        for ri in range(1, len(roads)):
            k0 = self.node_of[ri]
            d = np.hypot(main_x - self.x[k0], main_y - self.y[k0])
            j = int(main_ids[int(np.argmin(d))])
            edges.append((j, k0, float(max(d.min(), 0.05))))

        e = np.asarray(edges, dtype=np.int64)
        self.ea, self.eb, self.el = e[:, 0], e[:, 1], e[:, 2]

    def neighbours(self):
        nb = [[] for _ in range(self.n)]
        for a, b, L in zip(self.ea, self.eb, self.el):
            nb[a].append((b, L))
            nb[b].append((a, L))
        return nb

    def smooth(self, iters=60, lam=0.5):
        nb = self.neighbours()
        z = self.z_raw.copy()
        for _ in range(iters):
            acc = np.zeros_like(z)
            cnt = np.zeros_like(z)
            for i in range(self.n):
                if not nb[i]:
                    continue
                for j, _L in nb[i]:
                    acc[i] += z[j]
                    cnt[i] += 1.0
            m = cnt > 0
            z[m] += lam * (acc[m] / cnt[m] - z[m])
        return z

    def limit(self, z, max_deg, iters=400, tol=1e-4):
        """限坡投影：只往下降，反复裁 |Δh| ≤ tan(g)·长度，直到收敛。

        每条路按节点顺序做前向 + 后向扫描（高斯-赛德尔，收敛快），再处理路口短边。
        """
        cap = math.tan(math.radians(max_deg)) * self.ds
        capj = np.maximum(math.tan(math.radians(max_deg)) * self.el, 1e-3)
        z = z.copy()
        seqs = []
        ids = np.flatnonzero(np.diff(self.road) != 0) + 1
        starts = np.concatenate([[0], ids])
        ends = np.concatenate([ids, [self.n]])
        for a, b in zip(starts, ends):
            seqs.append(np.arange(a, b))
        junc = [(int(a), int(b), float(c)) for a, b, c in zip(self.ea, self.eb, capj)
                if abs(int(a) - int(b)) > 1]
        for _ in range(iters):
            changed = 0.0
            for seq in seqs:
                for i in range(1, len(seq)):
                    a, b = seq[i - 1], seq[i]
                    if z[b] > z[a] + cap:
                        changed = max(changed, z[b] - z[a] - cap)
                        z[b] = z[a] + cap
                for i in range(len(seq) - 2, -1, -1):
                    a, b = seq[i + 1], seq[i]
                    if z[b] > z[a] + cap:
                        changed = max(changed, z[b] - z[a] - cap)
                        z[b] = z[a] + cap
            for a, b, c in junc:
                cj = math.tan(math.radians(max_deg)) * c
                if z[b] > z[a] + cj:
                    changed = max(changed, z[b] - z[a] - cj)
                    z[b] = z[a] + cj
                elif z[a] > z[b] + cj:
                    changed = max(changed, z[a] - z[b] - cj)
                    z[a] = z[b] + cj
            if changed < tol:
                break
        return z


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ------------------------------------------------------------------ 主流程
def carve(args):
    bf = BaseField()
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    roads = build_roads(cfg)

    g = RoadGraph(bf, roads, args.ds)
    z_s = g.smooth(iters=args.smooth_iters, lam=0.5)
    z_lim = g.limit(z_s, args.max_grade)

    radius = bf.radius
    n = int(round(2 * radius / args.res)) + 1
    cell = 2 * radius / (n - 1)
    axis = -radius + np.arange(n) * cell
    gx, gy = np.meshgrid(axis, axis, indexing="xy")

    z_base = bf(gx, gy)
    half = max(w for _p, w, _n in roads) / 2.0
    r1 = half + args.shoulder + args.band

    pad = int(math.ceil((r1 + 2.0) / cell))
    ci0 = max(0, int((g.y.min() + radius) / cell) - pad)
    ci1 = min(n, int((g.y.max() + radius) / cell) + pad + 1)
    cj0 = max(0, int((g.x.min() + radius) / cell) - pad)
    cj1 = min(n, int((g.x.max() + radius) / cell) + pad + 1)

    w_acc = np.zeros((n, n), dtype=np.float64)
    z_node = np.zeros((n, n), dtype=np.float64)
    rows = np.arange(ci0, ci1)
    chunk = 48
    for s0 in range(ci0, ci1, chunk):
        rr = rows[s0 - ci0: s0 - ci0 + chunk]
        sx = gx[rr][:, cj0:cj1]
        sy = gy[rr][:, cj0:cj1]
        best_d = np.full(sx.shape, np.inf)
        best_z = np.zeros(sx.shape)
        for k in range(g.n):
            d = np.hypot(sx - g.x[k], sy - g.y[k])
            better = d < best_d
            if not better.any():
                continue
            best_d = np.where(better, d, best_d)
            best_z = np.where(better, z_lim[k], best_z)
        w = 1.0 - smoothstep((best_d - half - args.shoulder) / max(args.band, 1e-6))
        w_acc[rr[0]:rr[-1] + 1, cj0:cj1] = w
        z_node[rr[0]:rr[-1] + 1, cj0:cj1] = best_z

    z = (1.0 - w_acc) * z_base + w_acc * z_node
    data = np.clip((z - bf.base) / bf.elev, 0.0, 1.0).astype(np.float32)

    os.makedirs(os.path.dirname(OUT_NPZ), exist_ok=True)
    np.savez_compressed(OUT_NPZ, data=data, nrow=n, ncol=n, elev=bf.elev,
                        base=bf.base, radius=radius, cell=cell,
                        max_grade=args.max_grade, band=args.band)
    write_png(data, OUT_PNG)

    # ---- 统计（用路网节点上的最终高度） ----
    print("graph %d nodes, grid %dx%d (%.3f m/cell), radius %.1f, elev %.2f"
          % (g.n, n, n, cell, radius, bf.elev))
    print("%-10s %7s %5s %7s %7s %7s %7s %7s" %
          ("road", "len(m)", "w(m)", "g_mean", "g_p95", "g_max", "cut_m", "fill_m"))
    worst = 0.0
    for ri, (poly, width, name) in enumerate(roads):
        m = g.road == ri
        x, y, zr, zf = g.x[m], g.y[m], g.z_raw[m], z_lim[m]
        grade = np.degrees(np.arctan(np.abs(np.diff(zf)) / g.ds))
        worst = max(worst, float(grade.max()))
        print("%-10s %7.1f %5.1f %7.2f %7.2f %7.2f %7.2f %7.2f"
              % (name, float(g.ds * (m.sum() - 1)), width, float(grade.mean()),
                 float(np.percentile(grade, 95)), float(grade.max()),
                 float((zr - zf).max()), float((zf - zr).max())))
    print("worst grade on network: %.2f deg" % worst)

    changed = np.abs(z - z_base)
    print("corridor: %.1f%% of grid, max|dz| %.2f m, mean|dz| %.3f m"
          % (100.0 * (w_acc > 1e-3).mean(), changed.max(), changed[w_acc > 1e-3].mean()))
    return z


def write_png(data, path):
    """8-bit 灰度 PNG（不依赖 PIL）。

    实测：MuJoCo 读回的 `hfield_data` 相对文件行序是上下翻转的（用 flipud 对齐 rms 0.001），
    所以写文件时要先 `[::-1]`。
    """
    arr = (np.clip(data[::-1], 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    h, w = arr.shape
    raw = b"".join(b"\x00" + arr[i].tobytes() for i in range(h))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def apply_to_scenes(rel):
    patched = []
    for name in SCENES_TO_PATCH:
        p = os.path.join(ASSETS, name)
        if not os.path.exists(p):
            continue
        txt = open(p, encoding="utf-8").read()
        if rel in txt:
            continue
        new = txt.replace("terrain/height_field_patch.png", rel).replace(
            "height_field_patch.png", rel)
        if new != txt:
            open(p, "w", encoding="utf-8").write(new)
            patched.append(name)
    return patched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=float, default=0.6, help="目标格距（米）")
    ap.add_argument("--ds", type=float, default=0.25, help="路网节点间距")
    ap.add_argument("--max-grade", type=float, default=8.0, help="路面最大纵坡（度）")
    ap.add_argument("--band", type=float, default=6.0, help="路肩外过渡带宽度（米）")
    ap.add_argument("--shoulder", type=float, default=1.0, help="硬路肩（米）")
    ap.add_argument("--smooth-iters", type=int, default=160, help="路网高度平滑迭代")
    ap.add_argument("--apply", action="store_true", help="把场景 hfield 指到新 PNG")
    ap.add_argument("--out-npz", default="", help="另存 npz（默认 terrain/hf_road.npz）")
    ap.add_argument("--out-png", default="", help="另存 PNG（默认 terrain/height_field_road.png）")
    args = ap.parse_args()

    global OUT_NPZ, OUT_PNG
    if args.out_npz:
        OUT_NPZ = os.path.abspath(args.out_npz)
    if args.out_png:
        OUT_PNG = os.path.abspath(args.out_png)

    carve(args)
    print("wrote", os.path.relpath(OUT_NPZ, ASSETS), os.path.relpath(OUT_PNG, ASSETS))
    if args.apply:
        rel = os.path.relpath(OUT_PNG, ASSETS).replace("\\", "/")
        got = apply_to_scenes(rel)
        print("patched scenes:", ", ".join(got) if got else "(none)")


if __name__ == "__main__":
    main()
