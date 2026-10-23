# Flatten the terrain only under building footprints (with a transition band),
# keeping the surrounding mountain relief intact.
import argparse
import json
import os
import struct
import zlib

import mujoco
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def save_gray_png(path, data):
    h, w = data.shape
    raw = b"".join(b"\x00" + data[y].tobytes() for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ASSETS, "demo_v7.xml"))
    ap.add_argument("--out", dest="dst", default=os.path.join(ASSETS, "demo_v15.xml"))
    ap.add_argument("--config", default=os.path.join(ASSETS, "buildings.json"))
    ap.add_argument("--band", type=float, default=3.0)
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    xml = open(args.src, encoding="utf-8").read()
    m = mujoco.MjModel.from_xml_path(args.src)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)

    nrow, ncol = int(m.hfield_nrow[0]), int(m.hfield_ncol[0])
    extent = float(m.hfield_size[0, 0]) * 2.0
    relief = float(m.hfield_size[0, 2])
    base = float(m.hfield_size[0, 3])
    h = np.asarray(m.hfield_data).reshape(nrow, ncol).astype(np.float64)
    gg = np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8)

    def ground(x, y, exclude):
        gid = np.zeros(1, dtype=np.int32)
        dist = mujoco.mj_ray(m, d, np.array([x, y, 300.0]), np.array([0.0, 0.0, -1.0]),
                             gg, 1, exclude, gid)
        return None if dist < 0 else 300.0 - dist

    xs = -extent / 2 + np.arange(ncol) / (ncol - 1) * extent
    ys = -extent / 2 + np.arange(nrow) / (nrow - 1) * extent

    for p in cfg["plots"]:
        bid = p["id"]
        exclude = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, bid)
        W, D = p["size"][0] / 2.0, p["size"][1] / 2.0
        gs = [ground(p["x"] + sx * W, p["y"] + sy * D, exclude)
              for sx in (-1, 0, 1) for sy in (-1, 0, 1)]
        gs = [g for g in gs if g is not None]
        if not gs:
            continue
        platform = max(gs)
        pdata = np.clip((platform - base) / relief, 0.0, 1.0)

        for i in range(nrow):
            dy = abs(ys[i] - p["y"])
            if dy > D + args.band:
                continue
            for j in range(ncol):
                dx = abs(xs[j] - p["x"])
                if dx > W + args.band:
                    continue
                inside = dx <= W and dy <= D
                if inside:
                    h[i, j] = pdata
                else:
                    dist_out = max(dx - W, dy - D)
                    w = max(0.0, 1.0 - dist_out / args.band)
                    h[i, j] = h[i, j] * (1.0 - w) + pdata * w
        print(f"{bid}: platform={platform:.2f}")

    gray = np.clip(h[::-1, :] * 255.0, 0, 255).astype(np.uint8)
    png_path = os.path.join(ASSETS, "terrain", "dem_wenchuan_flat.png")
    save_gray_png(png_path, gray)
    xml = xml.replace('file="terrain/dem_wenchuan_200m.png"',
                      'file="terrain/dem_wenchuan_flat.png"')
    with open(args.dst, "w", encoding="utf-8") as f:
        f.write(xml)
    print("wrote", png_path, "and", args.dst)


if __name__ == "__main__":
    main()
