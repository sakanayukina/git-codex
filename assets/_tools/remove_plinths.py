# Remove the concrete plinth/base boxes that village.py puts under buildings.
import argparse
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    args = ap.parse_args()

    xml = open(args.src, encoding="utf-8").read()
    before = len(xml)
    for z in ("-0.55", "-0.35"):
        xml = re.sub(
            r'<geom[^>]*pos="0 0 ' + re.escape(z) + r'"[^>]*/>',
            "",
            xml,
        )
    with open(args.dst, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"removed {before - len(xml)} chars -> {args.dst}")


if __name__ == "__main__":
    main()
