"""Unified terrain sampling for hfield scenes and float DEM patches.

Two sources share the same height(x, y) interface:
    HfieldSampler(model_xml) : demo scenes (hfield), row 0 = -Y, relative height
    FloatDEMSampler(npz)     : Terrarium float truth, row 0 = +Y, shifted to relative

The row directions differ on purpose: MuJoCo's hfield_data is stored with row 0
at -Y, while fetch_dem.sample() returns a north-up window (row 0 at +Y).
"""
import os

import mujoco
import numpy as np


def _bilinear(z, fx, fy):
    nr, nc = z.shape
    c, r = fx * (nc - 1), fy * (nr - 1)
    r0, c0 = int(r), int(c)
    r1, c1 = min(r0 + 1, nr - 1), min(c0 + 1, nc - 1)
    dr, dc = r - r0, c - c0
    v = (z[r0, c0] * (1 - dr) * (1 - dc) + z[r1, c0] * dr * (1 - dc)
         + z[r0, c1] * (1 - dr) * dc + z[r1, c1] * dr * dc)
    return float(v)


class HfieldSampler:
    def __init__(self, model_xml):
        m = mujoco.MjModel.from_xml_path(model_xml)
        hid = next(g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD)
        fid = m.geom_dataid[hid]
        self.nr, self.nc = int(m.hfield_nrow[fid]), int(m.hfield_ncol[fid])
        self.sx, self.sy, self.sz, self.base = (float(v) for v in m.hfield_size[fid])
        self.px, self.py = float(m.geom_pos[hid][0]), float(m.geom_pos[hid][1])
        self.z = np.asarray(m.hfield_data).reshape(self.nr, self.nc)

    def height(self, x, y):
        fx = (x - self.px) / (2 * self.sx) + 0.5
        fy = (y - self.py) / (2 * self.sy) + 0.5
        if not (0 <= fx <= 1 and 0 <= fy <= 1):
            return None
        return self.base + _bilinear(self.z, fx, fy) * self.sz


class FloatDEMSampler:
    def __init__(self, npz_path):
        d = np.load(npz_path)
        z = np.asarray(d["z"], dtype=np.float64)
        self.z = z - float(z.min())
        self.extent = float(d["extent"])
        self.nr, self.nc = self.z.shape

    def height(self, x, y):
        fx = x / self.extent + 0.5
        fy = 0.5 - y / self.extent
        if not (0 <= fx <= 1 and 0 <= fy <= 1):
            return None
        return _bilinear(self.z, fx, fy)


def make_sampler(model_xml=None, dem_npz=None):
    if dem_npz:
        return FloatDEMSampler(dem_npz)
    if not model_xml:
        raise ValueError("model_xml or dem_npz is required")
    return HfieldSampler(model_xml)
