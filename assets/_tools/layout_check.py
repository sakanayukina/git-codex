r"""布局体检：房子是不是压在路上、彼此有没有撞在一起。

    python layout_check.py            # 读 assets/buildings.json

判据：房子边缘到路边的净空 < 0.5 m 就算压路（真实救灾场景里房子是不该骑在路面上的）。
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def closest_dist(px, py, pts):
    best, bd = None, 1e9
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy or 1e-6
        t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
        cx, cy = x0 + dx * t, y0 + dy * t
        d = math.hypot(px - cx, py - cy)
        if d < bd:
            best, bd = (cx, cy), d
    return best, bd


def radius_toward(plot, dx, dy):
    """房子沿 (dx,dy) 方向的投影半径（考虑 yaw 的旋转矩形）。"""
    a = math.radians(plot["yaw"])
    w, d = plot["size"][0] / 2, plot["size"][1] / 2
    # 把方向转到房子局部坐标
    lx = dx * math.cos(-a) - dy * math.sin(-a)
    ly = dx * math.sin(-a) + dy * math.cos(-a)
    L = math.hypot(lx, ly) or 1e-6
    lx, ly = lx / L, ly / L
    # 矩形在方向 (lx,ly) 上的支撑半径
    tx = w / abs(lx) if abs(lx) > 1e-6 else 1e9
    ty = d / abs(ly) if abs(ly) > 1e-6 else 1e9
    return min(tx, ty) if min(tx, ty) < 1e8 else max(tx, ty)


def main():
    cfg = json.load(open(os.path.join(ASSETS, "buildings.json"), encoding="utf-8"))
    pts, half_w = cfg["road"]["points"], cfg["road"]["width"] / 2
    print(f"路宽 {cfg['road']['width']} m（半宽 {half_w}）\n")

    bad = 0
    for p in cfg["plots"]:
        near, d = closest_dist(p["x"], p["y"], pts)
        dx, dy = near[0] - p["x"], near[1] - p["y"]
        r = radius_toward(p, dx, dy)
        clear = d - half_w - r
        tag = ""
        if clear < 0:
            tag = "  <-- 压在路上"
            bad += 1
        elif clear < 0.5:
            tag = "  <-- 贴边"
        print(f"{p['id']:<3} 中心({p['x']:>6.1f},{p['y']:>6.1f})  到路 {d:5.1f} m  "
              f"房子半径 {r:4.1f}  净空 {clear:5.1f} m{tag}")

    print()
    for i, a in enumerate(cfg["plots"]):
        for b in cfg["plots"][i + 1:]:
            gap = math.hypot(a["x"] - b["x"], a["y"] - b["y"]) - (
                max(a["size"][0], a["size"][1]) + max(b["size"][0], b["size"][1])) / 2
            if gap < 1.0:
                print(f"! {a['id']} 和 {b['id']} 挨得太近（间隙 {gap:.1f} m）")
                bad += 1

    print(f"\n问题数：{bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
