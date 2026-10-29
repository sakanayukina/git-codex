"""栅格地图 + A* 绕障规划（能力感知）。

从物理场景（village_duo.xml）导出：
  ① 610 个碰撞代理 → 2D 占据栅格（按机器人半径膨胀）
  ② hfield → 每格坡度（deg）
然后 A* 规划，把「坡度超过机器人包络」的格子视为不可通行。

    python nav_grid.py --all-sites                       # 从出生点到 H1..H7 的可达性与路径长度
    python nav_grid.py --from 1 -20 --to 15 -14          # 单条路径
    python nav_grid.py --all-sites --max-slope 5         # 按 Go2 学生包络（5°）规划
"""
import argparse
import heapq
import math
import os
import sys

import mujoco
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.join(BASE, "..", "village_duo.xml")

SITES = {
    "H1": (15.0, -14.0),
    "H2": (-24.0, -8.0),
    "H3": (-26.0, 24.0),
    "H4": (2.0, 36.0),
    "H5": (34.0, 2.0),
    "H6": (-12.0, -26.0),
    "H7": (-26.0, -44.0),
}


class NavGrid:
    def __init__(self, scene=SCENE, size=100.0, res=1.0, robot_radius=0.35):
        self.m = mujoco.MjModel.from_xml_path(scene)
        self.d = mujoco.MjData(self.m)
        mujoco.mj_forward(self.m, self.d)

        self.res = res
        self.half = size / 2.0
        self.n = int(size / res)
        self.origin = -self.half

        self.blocked = np.zeros((self.n, self.n), dtype=bool)
        self.slope = np.zeros((self.n, self.n), dtype=float)

        self._rasterize_props(robot_radius)
        self._sample_slope()

    # ---------- 栅格坐标 ----------
    def to_cell(self, x, y):
        i = int((y - self.origin) / self.res)
        j = int((x - self.origin) / self.res)
        return (min(max(i, 0), self.n - 1), min(max(j, 0), self.n - 1))

    def to_xy(self, cell):
        i, j = cell
        return (self.origin + (j + 0.5) * self.res, self.origin + (i + 0.5) * self.res)

    # ---------- 障碍 ----------
    def _rasterize_props(self, rr):
        """球：圆；盒子：按半长/半宽（考虑 yaw）铺矩形，再膨胀机器人半径。"""
        m, d = self.m, self.d
        hf = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
        cnt = 0
        for g in range(m.ngeom):
            if g == hf:
                continue
            gt = m.geom_type[g]
            if gt not in (mujoco.mjtGeom.mjGEOM_SPHERE, mujoco.mjtGeom.mjGEOM_BOX):
                continue
            p = d.geom_xpos[g]
            if abs(p[0]) > self.half or abs(p[1]) > self.half:
                continue
            if gt == mujoco.mjtGeom.mjGEOM_SPHERE:
                rad = float(m.geom_size[g][0]) + rr
                sx, sy = rad, rad
                yaw = 0.0
            else:
                a, b = float(m.geom_size[g][0]), float(m.geom_size[g][1])
                R = d.geom_xmat[g].reshape(3, 3)
                yaw = math.atan2(R[1, 0], R[0, 0])
                sx, sy = a + rr, b + rr
            ext = math.hypot(sx, sy)
            i0, j0 = self.to_cell(p[0] - ext, p[1] - ext)
            i1, j1 = self.to_cell(p[0] + ext, p[1] + ext)
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    x, y = self.to_xy((i, j))
                    dx, dy = x - p[0], y - p[1]
                    if gt == mujoco.mjtGeom.mjGEOM_SPHERE:
                        if dx * dx + dy * dy <= sx * sx:
                            self.blocked[i, j] = True
                    else:
                        c, s = math.cos(-yaw), math.sin(-yaw)
                        lx = c * dx - s * dy
                        ly = s * dx + c * dy
                        if abs(lx) <= sx and abs(ly) <= sy:
                            self.blocked[i, j] = True
            cnt += 1
        self.n_props = cnt

    def nearest_free(self, xy, max_r=4.0, max_slope=None):
        """在 xy 附近找一个可通行格（用于把「废墟中心」这类目标点挪到门口空地）。"""
        si, sj = self.to_cell(*xy)
        best, best_d = None, 1e9
        rad = int(max_r / self.res)
        for di in range(-rad, rad + 1):
            for dj in range(-rad, rad + 1):
                i, j = si + di, sj + dj
                if not (0 <= i < self.n and 0 <= j < self.n):
                    continue
                if self.blocked[i, j]:
                    continue
                if max_slope is not None and self.slope[i, j] > max_slope:
                    continue
                x, y = self.to_xy((i, j))
                dd = (x - xy[0]) ** 2 + (y - xy[1]) ** 2
                if dd < best_d:
                    best, best_d = (i, j), dd
        return best

    # ---------- 坡度 ----------
    def _sample_slope(self):
        hf = next(g for g in range(self.m.ngeom) if self.m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
        gid = np.array([-1], dtype=np.int32)
        grp = np.ones(6, dtype=np.uint8)

        def h(x, y):
            dist = mujoco.mj_ray(self.m, self.d, np.array([x, y, 300.0]),
                                 np.array([0, 0, -1.0]), grp, 1, -1, gid)
            return 300.0 - dist if (dist > 0 and int(gid[0]) == hf) else np.nan

        step = 1.0
        for i in range(self.n):
            for j in range(self.n):
                x, y = self.to_xy((i, j))
                z0 = h(x, y)
                zx = h(x + step, y)
                zy = h(x, y + step)
                if np.isnan(z0) or np.isnan(zx) or np.isnan(zy):
                    self.slope[i, j] = 90.0
                    continue
                gx = (zx - z0) / step
                gy = (zy - z0) / step
                self.slope[i, j] = math.degrees(math.atan(math.hypot(gx, gy)))

    # ---------- A* ----------
    def segment_clear(self, p0, p1, max_slope):
        """Sample a straight segment and verify every touched cell is passable."""
        distance = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        steps = max(2, int(math.ceil(distance / (self.res * 0.5))))
        for k in range(steps + 1):
            t = k / steps
            x = p0[0] + (p1[0] - p0[0]) * t
            y = p0[1] + (p1[1] - p0[1]) * t
            cell = self.to_cell(x, y)
            if self.blocked[cell] or self.slope[cell] > max_slope:
                return False
        return True

    def simplify(self, points, max_slope):
        """Line-of-sight shortcutting: fewer turns without leaving free cells."""
        if len(points) <= 2:
            return list(points)
        result = [points[0]]
        current = 0
        while current < len(points) - 1:
            nxt = len(points) - 1
            while nxt > current + 1 and not self.segment_clear(
                    points[current], points[nxt], max_slope):
                nxt -= 1
            result.append(points[nxt])
            current = nxt
        return result

    def plan(self, start_xy, goal_xy, max_slope=15.0, slope_soft=8.0):
        s = None
        for rad in (4.0, 8.0, 15.0, 25.0):
            s = self.nearest_free(start_xy, rad, max_slope)
            if s is not None:
                break
        g = None
        for rad in (4.0, 8.0, 15.0, 25.0):
            g = self.nearest_free(goal_xy, rad, max_slope)
            if g is not None:
                break
        if s is None:
            return None, "起点附近 25 m 内无可通行格"
        if g is None:
            return None, "目标附近 25 m 内无可通行格"

        def passable(c):
            return (not self.blocked[c]) and self.slope[c] <= max_slope

        if not passable(s) or not passable(g):
            return None, "起点或终点坡度超限"

        def hcost(c):
            ax, ay = self.to_xy(c)
            return math.hypot(ax - goal_xy[0], ay - goal_xy[1])

        openq = [(hcost(s), 0.0, s)]
        came, gcost = {}, {s: 0.0}
        found = False
        while openq:
            _, gc, cur = heapq.heappop(openq)
            if cur == g:
                found = True
                break
            if gc > gcost.get(cur, 1e18):
                continue
            ci, cj = cur
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if di == 0 and dj == 0:
                        continue
                    nb = (ci + di, cj + dj)
                    if not (0 <= nb[0] < self.n and 0 <= nb[1] < self.n):
                        continue
                    if not passable(nb):
                        continue
                    step = math.hypot(di, dj) * self.res
                    pen = 1.0
                    if self.slope[nb] > slope_soft:
                        pen = 3.0                      # 陡坡加代价（能走但慢）
                    ng = gc + step * pen
                    if ng < gcost.get(nb, 1e18):
                        gcost[nb] = ng
                        came[nb] = cur
                        heapq.heappush(openq, (ng + hcost(nb), ng, nb))
        if not found:
            return None, "无可行路径（被障碍或陡坡切断）"

        path = [g]
        while path[-1] != s:
            path.append(came[path[-1]])
        path.reverse()
        xy = [self.to_xy(c) for c in path]
        raw_length = sum(
            math.hypot(xy[k + 1][0] - xy[k][0], xy[k + 1][1] - xy[k][1])
            for k in range(len(xy) - 1))
        raw_cells = len(xy)
        xy = self.simplify(xy, max_slope)
        length = sum(math.hypot(xy[k + 1][0] - xy[k][0], xy[k + 1][1] - xy[k][1])
                     for k in range(len(xy) - 1))
        slopes = [self.slope[c] for c in path]
        maxs = max(slopes)
        # 持续坡度：沿路径按 5 m 窗口（约 5 格）滑动平均，取最大值
        win = max(2, int(5.0 / self.res))
        sust = max(sum(slopes[k:k + win]) / len(slopes[k:k + win])
                   for k in range(max(1, len(slopes) - win + 1)))
        gx, gy = self.to_xy(g)
        park = math.hypot(gx - goal_xy[0], gy - goal_xy[1])
        return dict(points=xy, length=length, raw_length=raw_length,
                    max_slope=maxs, sustained=sust, park=park,
                    cells=len(xy), raw_cells=raw_cells, cost=gcost[g]), "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", nargs=2, type=float, default=[1.0, -20.0])
    ap.add_argument("--to", dest="goal", nargs=2, type=float, default=None)
    ap.add_argument("--all-sites", action="store_true")
    ap.add_argument("--max-slope", type=float, default=25.0, help="超过该坡度视为不可通行")
    ap.add_argument("--slope-soft", type=float, default=10.0, help="超过该坡度加大代价")
    ap.add_argument("--res", type=float, default=1.0)
    ap.add_argument("--radius", type=float, default=0.35, help="机器人半径（Go2 半宽约 0.25，加安全余量）")
    a = ap.parse_args()

    grid = NavGrid(res=a.res, robot_radius=a.radius)
    print("栅格 %dx%d，分辨率 %.1f m，障碍格 %d/%d（%.1f%%），代理 %d 个"
          % (grid.n, grid.n, grid.res, int(grid.blocked.sum()), grid.blocked.size,
             100.0 * grid.blocked.mean(), grid.n_props))
    print("坡度：中位 %.1f°，p95 %.1f°" % (np.median(grid.slope), np.percentile(grid.slope, 95)))
    print()

    if a.all_sites:
        print("%-4s %7s %8s %7s %8s %8s %s" % ("site", "直线", "路径长", "绕行比", "最大坡度", "持续坡度", "状态"))
        for name, xy in SITES.items():
            straight = math.hypot(xy[0] - a.start[0], xy[1] - a.start[1])
            r, msg = grid.plan(a.start, xy, max_slope=a.max_slope, slope_soft=a.slope_soft)
            if r is None:
                print("%-4s %6.1fm %8s %7s %8s %8s %s" % (name, straight, "-", "-", "-", "-", msg))
            else:
                print("%-4s %6.1fm %7.1fm %6.2fx %7.1f° %7.1f° 停在 %.1fm 外"
                      % (name, straight, r["length"], r["length"] / max(straight, 1e-6),
                         r["max_slope"], r["sustained"], r["park"]))
        return

    goal = a.goal if a.goal else SITES["H1"]
    r, msg = grid.plan(a.start, goal, max_slope=a.max_slope, slope_soft=a.slope_soft)
    if r is None:
        print("起点", a.start, "→ 目标", goal, "：", msg)
        return
    print("起点 %s → 目标 %s" % (a.start, goal))
    print("可执行路径 %.1f m（原始 %.1f m），%d 个航点（原始 %d 格），最大坡度 %.1f°"
          % (r["length"], r["raw_length"], r["cells"],
             r["raw_cells"], r["max_slope"]))
    print("前 8 个航点:", [tuple(round(v, 1) for v in p) for p in r["points"][:8]])


if __name__ == "__main__":
    main()
