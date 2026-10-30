"""路网走廊判定：某个 (x, y) 是否在村道走廊内（给代理生成 / 道具清理 / 规划共用）。

走廊 = 路中心线 ± 半宽（主路 2.1 m、支路 1.5 m）。比 `carve_roads.py` 的
"可走走廊"窄，因为这里关心的是"会不会挡住机器人的脚"。

    from roadmask import RoadMask
    rm = RoadMask()
    rm.intrudes(x, y, radius=1.8)     # 这个半径 1.8 m 的石头会不会伸进路面
    rm.free(x, y, margin=0.5)         # 离路面边缘还差 0.5 m 以上
"""
import json
import math
import os

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.normpath(os.path.join(BASE, ".."))
CONFIG = os.path.join(ASSETS, "buildings.json")


def _roads(cfg):
    main_pts = [(float(a), float(b)) for a, b in cfg["road"]["points"]]
    roads = [(main_pts, float(cfg["road"]["width"]))]
    for p in cfg.get("plots", []):
        a = math.radians(p["yaw"])
        dx, dy = math.sin(a) * p["size"][1] / 2, -math.cos(a) * p["size"][1] / 2
        door = (p["x"] + dx, p["y"] + dy)
        best, bd = None, 1e9
        for (x0, y0), (x1, y1) in zip(main_pts, main_pts[1:]):
            ux, uy = x1 - x0, y1 - y0
            L2 = ux * ux + uy * uy or 1e-6
            t = max(0.0, min(1.0, ((door[0] - x0) * ux + (door[1] - y0) * uy) / L2))
            cx, cy = x0 + ux * t, y0 + uy * t
            d = math.hypot(door[0] - cx, door[1] - cy)
            if d < bd:
                best, bd = (cx, cy), d
        if best is None or bd < 1.0:
            continue
        mid = ((door[0] + best[0]) / 2.0, (door[1] + best[1]) / 2.0)
        roads.append(([best, mid, door], 3.0))
    return roads


class RoadMask:
    def __init__(self, config=CONFIG, margin=0.0):
        cfg = json.load(open(config, encoding="utf-8"))
        self.segs = []
        for poly, width in _roads(cfg):
            for (x0, y0), (x1, y1) in zip(poly, poly[1:]):
                self.segs.append((x0, y0, x1, y1, width / 2.0))
        self.margin = margin

    def nearest(self, x, y):
        best_d, best_half = 1e9, 0.0
        for x0, y0, x1, y1, half in self.segs:
            ux, uy = x1 - x0, y1 - y0
            L2 = ux * ux + uy * uy or 1e-9
            t = max(0.0, min(1.0, ((x - x0) * ux + (y - y0) * uy) / L2))
            d = math.hypot(x - (x0 + ux * t), y - (y0 + uy * t))
            if d - half < best_d - best_half:
                best_d, best_half = d, half
        return best_d, best_half

    def clearance(self, x, y):
        d, half = self.nearest(x, y)
        return d - half

    def free(self, x, y, margin=None):
        m = self.margin if margin is None else margin
        return self.clearance(x, y) > m

    def intrudes(self, x, y, radius=0.0, margin=None):
        m = self.margin if margin is None else margin
        return self.clearance(x, y) < radius + m


if __name__ == "__main__":
    rm = RoadMask()
    for pt in [(3.6, -22.0), (0.0, 0.0), (15.0, -14.0), (-24.0, -8.0)]:
        print("%7.2f %7.2f  clearance %6.2f m  %s"
              % (pt[0], pt[1], rm.clearance(*pt), "road" if rm.free(*pt) else "off-road"))
