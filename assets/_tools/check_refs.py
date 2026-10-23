import re, os, sys

XML = sys.argv[1] if len(sys.argv) > 1 else "demo_v19.xml"
x = open(XML, encoding="utf-8").read()
refs = sorted(set(re.findall(r'file="([^"]+)"', x)))
missing = [r for r in refs if not os.path.exists(r)]
print(f"referenced: {len(refs)}  missing: {len(missing)}")
for m in missing:
    print("   MISSING", m)
tex = [r for r in refs if r.lower().endswith((".png", ".jpg", ".jpeg"))]
print("textures:", len(tex))
# 每个贴图被多少个 material 引用
from collections import Counter
c = Counter(re.findall(r'<material[^>]*texture="([^"]+)"', x))
print("materials with textures:", sum(c.values()), "distinct tex names:", len(c))
