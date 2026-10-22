r"""给单面片模型补"背面"：复制面 + 翻转法线，解决树叶近看发白点。

MuJoCo 不做背面剔除，但背面用的是正面法线，光照会算错 → 看起来发亮/发白。
把每个面反向复制一份、并给一份反向法线，两面就都正常了。

    python double_side.py --in ..\props\imported\maple\maple_sugar_maple_leaf.obj
    python double_side.py --in <obj> --apply     # 就地写入（.bak 备份）
"""
import argparse
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.dirname(HERE)


def parse(path):
    v, vt, vn, faces = [], [], [], []
    for ln in open(path, encoding="utf-8", errors="ignore"):
        if ln.startswith("v "):
            v.append(ln.rstrip())
        elif ln.startswith("vt "):
            vt.append(ln.rstrip())
        elif ln.startswith("vn "):
            vn.append(ln.rstrip())
        elif ln.startswith("f "):
            faces.append(ln.rstrip())
    return v, vt, vn, faces


def split_face(line):
    """'f a/b/c d/e/f g/h/i' -> [[a,b,c],[d,e,f],[g,h,i]]（允许缺项）"""
    toks = line.split()[1:]
    out = []
    for t in toks:
        parts = t.split("/")
        while len(parts) < 3:
            parts.append("")
        out.append(parts)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    v, vt, vn, faces = parse(args.src)
    n_vn = len(vn)

    # 反向法线：接在末尾
    flipped_vn = []
    for line in vn:
        parts = line.split()
        flipped_vn.append(f"vn {-float(parts[1]):.4f} {-float(parts[2]):.4f} {-float(parts[3]):.4f}".replace("-0.0000", "0.0000"))

    back_faces = []
    for line in faces:
        tri = split_face(line)
        if len(tri) != 3:
            continue
        rev = list(reversed(tri))
        out = []
        for (vi, ti, ni) in rev:
            # 法线指向新追加的那组（原索引 + n_vn）
            new_ni = str(int(ni) + n_vn) if ni else ""
            out.append(f"{vi}/{ti}/{new_ni}" if ti else f"{vi}//{new_ni}")
        back_faces.append("f " + " ".join(out))

    print(f"{os.path.basename(args.src)}: {len(v)} v, {len(vn)} vn, {len(faces)} f")
    print(f"  -> add {len(flipped_vn)} flipped vn, {len(back_faces)} back faces")
    if not args.apply:
        print("(dry run; add --apply)")
        return

    backup = args.src + ".bak"
    os.replace(args.src, backup) if not os.path.exists(backup) else None
    with open(args.src, "w", encoding="utf-8") as fh:
        for ln in v + vt + vn + flipped_vn:
            fh.write(ln + "\n")
        for ln in faces + back_faces:
            fh.write(ln + "\n")
    print(f"wrote {os.path.relpath(args.src, ASSETS)} (backup: {os.path.basename(backup)})")


if __name__ == "__main__":
    main()
