# Thin out and slim the procedural conifers in an already-built scene.
# Real maple trees (maple_*) are left untouched.
import argparse
import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ASSETS, "demo_v6.xml"))
    ap.add_argument("--out", dest="dst", default=os.path.join(ASSETS, "demo_v7.xml"))
    ap.add_argument("--keep", type=int, default=90)
    ap.add_argument("--slender", type=float, default=0.72)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    xml = open(args.src, encoding="utf-8").read()
    rng = np.random.default_rng(args.seed)

    pattern = re.compile(r'<body name="(tree(?:_x|_v)?\d+)"[^>]*>.*?</body>', re.S)
    matches = list(pattern.finditer(xml))
    print(f"procedural trees found: {len(matches)}")

    if len(matches) > args.keep:
        keep_idx = set(rng.choice(len(matches), args.keep, replace=False))
    else:
        keep_idx = set(range(len(matches)))

    def slender_body(body):
        def repl(m):
            vals = [float(v) for v in m.group(1).split()]
            if len(vals) != 3:
                return m.group(0)
            return (f'size="{vals[0] * args.slender:.3f} '
                    f'{vals[1] * args.slender:.3f} {vals[2]:.3f}"')
        return re.sub(r'size="([\d.]+ [\d.]+ [\d.]+)"', repl, body)

    removed = 0
    for i in reversed(range(len(matches))):
        m = matches[i]
        if i in keep_idx:
            new = slender_body(m.group(0))
        else:
            new = ""
            removed += 1
        xml = xml[:m.start()] + new + xml[m.end():]

    with open(args.dst, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"kept {args.keep}, removed {removed}, wrote {args.dst}")


if __name__ == "__main__":
    main()
