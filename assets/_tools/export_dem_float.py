r"""导出 float 高度场真值（Terrarium 16 位精度），供地形采样脚本共读。

    python export_dem_float.py                 # 用默认场地参数（与 dem_wenchuan_flat.png 同源）
    python export_dem_float.py --half 100 --px 256

产物 terrain/dem_float.npz，字段：
    z        (H,W) float32  海拔（米），row 0 = +Y（北），与 polish.terrain_fn 约定一致
    extent   float          边长（米）
    htype    uint8          高度场类型：0=hfield（8 位，有 0.26 m 量化），1=float
    lat/lon  float          中心经纬度
    zoom     int            Terrarium 层级

为什么要它：现在场景用的 8 位 PNG 每级 0.26 m，是假台阶；采样脚本（flatten_sites /
reground_props / fix_grounding / seam_ring / polish）应该读这份 float 真值，避免在
量化误差上做决策。
"""
import argparse
import os

import numpy as np

import fetch_dem

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=31.055)
    ap.add_argument("--lon", type=float, default=103.483)
    ap.add_argument("--half", type=float, default=100.0, help="半宽（米），200 m 场景填 100")
    ap.add_argument("--zoom", type=int, default=0, help="0=按范围自动")
    ap.add_argument("--out", default=os.path.join(ASSETS, "terrain", "dem_float.npz"))
    a = ap.parse_args()

    # fetch_tile 里把 TILE_CACHE 当全局用，但它在 fetch_dem.main() 里是局部变量，这里补上
    fetch_dem.TILE_CACHE = os.path.join(HERE, "_tiles")
    z = a.zoom or 15
    h, extent = fetch_dem.sample(z, a.half, a.lat, a.lon)
    h = np.nan_to_num(h, nan=float(np.nanmin(h[np.isfinite(h)])) if np.isfinite(h).any() else 0.0)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    np.savez_compressed(a.out, z=h.astype(np.float32), extent=float(extent),
                        htype=np.uint8(1), lat=a.lat, lon=a.lon, zoom=int(z))
    print("DEM %dx%d, %.1f m 见方, 层级 z=%d" % (h.shape[1], h.shape[0], extent, z))
    print("海拔 %.1f .. %.1f m（落差 %.1f m）" % (h.min(), h.max(), h.max() - h.min()))
    q = (h.max() - h.min()) / 255.0
    print("对比：8 位量化每级 %.3f m（这就是假台阶的来源）" % q)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
