import os
import glob
import sys

import pypdf

SRC_DIR = r"C:\Users\18967\Desktop\论文"
OUT_DIR = r"C:\Users\18967\Desktop\git\papers"


def extract_with_pypdf(path):
    reader = pypdf.PdfReader(path)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts), len(reader.pages)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(SRC_DIR, "*.pdf")))
    if not files:
        print("No PDFs found in", SRC_DIR)
        sys.exit(1)
    for i, path in enumerate(files, 1):
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            text, pages = extract_with_pypdf(path)
            chars = len(text.strip())
            out_name = f"{i:02d}_{name}.txt"
            with open(os.path.join(OUT_DIR, out_name), "w", encoding="utf-8") as f:
                f.write(text)
            print(f"[{i}] {name} | pages={pages} | chars={chars}")
        except Exception as e:
            print(f"[{i}] {name} | ERROR: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
