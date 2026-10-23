# Smooth an 8-bit hfield PNG to reduce stair-stepping and local slope spikes.
# Usage: python smooth_terrain.py [sigma]
import os
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)

src = os.path.join(ASSETS, "terrain", "dem_wenchuan_200m.png")
dst = os.path.join(ASSETS, "terrain", "dem_wenchuan_200m_smooth.png")
sigma = float(sys.argv[1]) if len(sys.argv) > 1 else 1.5

g = np.asarray(Image.open(src).convert("L"), dtype=np.float64)
s = gaussian_filter(g, sigma=sigma)
s = np.clip(s, 0, 255).astype(np.uint8)
Image.fromarray(s, mode="L").save(dst)

print(f"sigma={sigma} range {g.min():.0f}..{g.max():.0f} -> {s.min()}..{s.max()}")
print("wrote", dst, s.shape)
