"""Gently smooth an 8-bit MuJoCo hfield while preserving broad terrain shape."""
import argparse
import os

import numpy as np
from PIL import Image, ImageFilter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--out", help="output PNG; defaults to in-place")
    parser.add_argument("--radius", type=float, default=1.0,
                        help="Gaussian blur radius in height-map pixels")
    parser.add_argument("--blend", type=float, default=0.5,
                        help="fraction of smoothed image mixed into the result")
    args = parser.parse_args()
    out = args.out or args.image

    original = Image.open(args.image).convert("L")
    smoothed = original.filter(ImageFilter.GaussianBlur(radius=args.radius))
    result = Image.blend(
        original, smoothed, max(0.0, min(1.0, args.blend)))
    result.save(out)

    before = np.asarray(original, dtype=np.float32)
    after = np.asarray(result, dtype=np.float32)
    print("smoothed %s -> %s | mean_abs_delta=%.3f gray | max_delta=%.0f" %
          (os.path.basename(args.image), os.path.basename(out),
           float(np.mean(np.abs(after - before))),
           float(np.max(np.abs(after - before)))))


if __name__ == "__main__":
    main()
