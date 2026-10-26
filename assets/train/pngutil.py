"""最小 PNG 写入（mujoco 环境没有 PIL）。"""
import struct
import zlib

NUL = bytes([0])
SIG = bytes([137, 80, 78, 71, 13, 10, 26, 10])


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def save_rgb(arr, path):
    h, w = arr.shape[:2]
    raw = b"".join(NUL + arr[y, :, :3].astype("uint8").tobytes() for y in range(h))
    blob = (SIG
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 6))
            + _chunk(b"IEND", b""))
    open(path, "wb").write(blob)
