"""把 ICO 转成 PNG / 缩放（纯标准库，无第三方依赖）。

用途：程序图标来自 `assets/KGSaveManager.ico`（多尺寸 BMP 格式的 ICO），
exe 直接用它；HTML 版需要 PNG（favicon 与 manifest），这里负责转换与缩放。

用法：
    python tools/ico_to_png.py <输入.ico> <输出.png> [尺寸]

- 不指定尺寸时导出 ICO 里最大的那一张；
- 指定尺寸时按盒式平均缩放（只缩小，不放大）。
"""

import struct
import sys
import zlib
from pathlib import Path


# ---------------- ICO 解码 ----------------
def ico_entries(raw):
    """返回 [(宽, 高, 位深, 数据偏移, 数据长度)]。"""
    reserved, itype, count = struct.unpack("<HHH", raw[:6])
    if reserved != 0 or itype != 1:
        raise ValueError("不是 ICO 文件")
    out = []
    for i in range(count):
        w, h, _colors, _r, _planes, bpp, size, offset = struct.unpack(
            "<BBBBHHII", raw[6 + 16 * i:22 + 16 * i])
        out.append((w or 256, h or 256, bpp, offset, size))
    return out


def decode_entry(raw, entry):
    """把一条 ICO 记录解成 (宽, 高, [(r,g,b,a) 行])。

    支持 32bpp 未压缩 DIB（本项目的图标就是这种）；PNG 存储的记录直接透传
    （返回 None，由调用方按文件写出）。
    """
    width, height, bpp, offset, size = entry
    blob = raw[offset:offset + size]
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return None
    if bpp != 32:
        raise ValueError(f"只支持 32bpp 的 DIB 记录，实际 {bpp}bpp")

    header_size = struct.unpack("<I", blob[:4])[0]
    if header_size < 40:
        raise ValueError(f"不支持的 DIB 头（{header_size} 字节）")
    (bi_w, bi_h, planes, bitcount, compression, _img_size) = struct.unpack(
        "<iiHHII", blob[4:24])
    if bitcount != 32 or compression != 0:
        raise ValueError(f"不支持的位深/压缩：{bitcount}bpp comp={compression}")

    # ICO 里 biHeight 是 XOR + AND 两张图的高度之和
    height_px = bi_h // 2
    stride = bi_w * 4
    pixels = []
    for y in range(height_px):
        # DIB 自底向上存储
        row_start = header_size + (height_px - 1 - y) * stride
        row = []
        for x in range(bi_w):
            b, g, r, a = blob[row_start + x * 4: row_start + x * 4 + 4]
            row.append((r, g, b, a))
        pixels.append(row)
    if width != bi_w or height != height_px:
        raise ValueError(f"记录尺寸与 DIB 不一致：{width}x{height} vs "
                         f"{bi_w}x{height_px}")
    return bi_w, height_px, pixels


# ---------------- PNG 写出 ----------------
def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path, width, height, pixels):
    raw = b"".join(
        b"\x00" + bytes(v for px in row for v in px) for row in pixels)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    data = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) +
            _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))
    Path(path).write_bytes(data)
    return len(data)


def scale(pixels, src_size, dst_size):
    """盒式平均缩放（只缩小）。"""
    if dst_size == src_size:
        return pixels
    if dst_size > src_size:
        raise ValueError("不放大：目标尺寸不能大于源尺寸")
    factor = src_size / dst_size
    out = []
    for y in range(dst_size):
        y0, y1 = int(y * factor), max(int((y + 1) * factor), int(y * factor) + 1)
        row = []
        for x in range(dst_size):
            x0 = int(x * factor)
            x1 = max(int((x + 1) * factor), x0 + 1)
            r = g = b = a = n = 0
            for sy in range(y0, min(y1, src_size)):
                for sx in range(x0, min(x1, src_size)):
                    pr, pg, pb, pa = pixels[sy][sx]
                    r += pr * pa
                    g += pg * pa
                    b += pb * pa
                    a += pa
                    n += 1
            if a == 0 or n == 0:
                row.append((0, 0, 0, 0))
            else:
                row.append((round(r / a), round(g / a), round(b / a),
                            round(a / n)))
        out.append(row)
    return out


def largest_entry(raw):
    entries = ico_entries(raw)
    return max(entries, key=lambda e: e[0] * e[1])


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    src = Path(argv[1])
    dst = Path(argv[2])
    size = int(argv[3]) if len(argv) > 3 else None
    raw = src.read_bytes()
    entry = largest_entry(raw)
    decoded = decode_entry(raw, entry)
    if decoded is None:
        dst.write_bytes(raw[entry[3]:entry[3] + entry[4]])
        print(f"{dst.name}: 源记录本身是 PNG，已直接写出")
        return 0
    width, height, pixels = decoded
    if size and size != width:
        pixels = scale(pixels, width, size)
        width = height = size
    written = write_png(dst, width, height, pixels)
    print(f"{dst.name}: {width}x{height}, {written} 字节")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
