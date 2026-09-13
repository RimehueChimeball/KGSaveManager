"""生成前端图标（纯标准库，无第三方依赖）。

产出：
- `webapp/assets/favicon.ico`：多尺寸（16/32/48/64）PNG 压缩的 ICO
- `webapp/assets/icon-192.png`：给 manifest 用的大图

用法（仓库根目录）：
    python tools/make_favicon.py

图案：蓝底圆角方块 + 白色猫头（两只耳朵），对应 Kittens Game。
所有绘制用 4 倍超采样后缩算，边缘比较平滑。
"""

import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "webapp" / "assets"

ACCENT = (47, 111, 221)          # 与 style.css 的 --accent 一致
INK = (255, 255, 255)
SS = 4                           # 超采样倍数


# ---------------- PNG 写出 ----------------
def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def png_bytes(width, height, pixels):
    """pixels: 每行是 [(r,g,b,a), ...] 的列表。"""
    raw = b"".join(
        b"\x00" + bytes(v for px in row for v in px) for row in pixels)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" +
            _chunk(b"IHDR", ihdr) +
            _chunk(b"IDAT", zlib.compress(raw, 9)) +
            _chunk(b"IEND", b""))


# ---------------- 画图 ----------------
def _inside_rounded(x, y, size, radius):
    r = radius
    if x < r and y < r:
        return (r - x) ** 2 + (r - y) ** 2 <= r * r
    if x > size - r and y < r:
        return (x - (size - r)) ** 2 + (r - y) ** 2 <= r * r
    if x < r and y > size - r:
        return (r - x) ** 2 + (y - (size - r)) ** 2 <= r * r
    if x > size - r and y > size - r:
        return ((x - (size - r)) ** 2 + (y - (size - r)) ** 2) <= r * r
    return True


def _inside_triangle(px, py, a, b, c):
    def sign(p1, p2, p3):
        return ((p1[0] - p3[0]) * (p2[1] - p3[1]) -
                (p2[0] - p3[0]) * (p1[1] - p3[1]))
    d1 = sign((px, py), a, b)
    d2 = sign((px, py), b, c)
    d3 = sign((px, py), c, a)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def draw(size):
    """返回 size×size 的 RGBA 像素（超采样后缩算）。"""
    big = size * SS
    grid = [[(0, 0, 0, 0)] * big for _ in range(big)]
    radius = big * 0.22
    cx, cy, hr = big * 0.5, big * 0.56, big * 0.26      # 猫头圆心与半径
    ear_l = ((big * 0.24, big * 0.44), (big * 0.30, big * 0.15),
             (big * 0.50, big * 0.34))
    ear_r = ((big * 0.76, big * 0.44), (big * 0.70, big * 0.15),
             (big * 0.50, big * 0.34))

    for y in range(big):
        for x in range(big):
            px, py = x + 0.5, y + 0.5
            if not _inside_rounded(px, py, big, radius):
                continue
            color = ACCENT + (255,)
            head = (px - cx) ** 2 + (py - cy) ** 2 <= hr * hr
            if head or _inside_triangle(px, py, *ear_l) or \
                    _inside_triangle(px, py, *ear_r):
                color = INK + (255,)
            grid[y][x] = color

    # 缩算（盒式平均）
    out = []
    for y in range(size):
        row = []
        for x in range(size):
            r = g = b = a = 0
            for dy in range(SS):
                for dx in range(SS):
                    pr, pg, pb, pa = grid[y * SS + dy][x * SS + dx]
                    r += pr * pa
                    g += pg * pa
                    b += pb * pa
                    a += pa
            n = SS * SS
            if a == 0:
                row.append((0, 0, 0, 0))
            else:
                row.append((round(r / a), round(g / a), round(b / a),
                            round(a / n)))
        out.append(row)
    return out


# ---------------- ICO 容器 ----------------
def ico_bytes(images):
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    blobs = b""
    for size, data in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                               len(data), offset)
        offset += len(data)
        blobs += data
    return header + entries + blobs


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    sizes = (16, 32, 48, 64)
    images = [(s, png_bytes(s, s, draw(s))) for s in sizes]
    ico = ASSETS / "favicon.ico"
    ico.write_bytes(ico_bytes(images))
    big = png_bytes(192, 192, draw(192))
    png = ASSETS / "icon-192.png"
    png.write_bytes(big)
    print(f"写出 {ico.name}（{ico.stat().st_size} 字节，含 "
          f"{'/'.join(str(s) for s in sizes)}）")
    print(f"写出 {png.name}（{png.stat().st_size} 字节，192×192）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
