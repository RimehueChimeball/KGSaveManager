"""
savecodec：Kittens Game 存档（lz-string 压缩）的 Python 解码与校验。

移植自游戏自带 lib/lz-string.js（v1.4.4）的解压路径：
- decompressFromBase64：LZString._decompress(len, 32, base64 逆映射)
- decompressFromUTF16 ：LZString._decompress(len, 16384, charCodeAt-32)

用途：手动存档粘贴/导入前校验“是否疑似合法存档”（可能/疑似不合法提示），
存档文件本身仍原样保存，不重新编码。
"""

import json

_B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
_B64_REVERSE = {ch: i for i, ch in enumerate(_B64_ALPHABET)}


def _decompress(length, reset_value, get_next):
    """移植 LZString._decompress。成功返回字符串；失败/损坏返回 None。"""
    dictionary = [None, None, None]   # 压缩器第 0..2 码是标志位，不会作为引用
    enlarge_in = 4
    num_bits = 3
    entry = ""
    result = []
    val = get_next(0)
    position = reset_value
    index = 1

    def read_bits(bits):
        nonlocal val, position, index
        s = 0
        power = 1
        for _ in range(bits):
            bit = 1 if (val & position) else 0
            position >>= 1
            if position == 0:
                position = reset_value
                if index >= length:
                    return None
                val = get_next(index)
                index += 1
            if bit:
                s += power
            power <<= 1
        return s

    def read_char(bits):
        s = read_bits(bits)
        if s is None:
            return None
        return chr(s)

    # 首位：2 位标志 -> 8/16 位字符 / 空串
    head = read_bits(2)
    if head is None:
        return None
    if head == 2:
        return ""
    if head == 0:
        first = read_char(8)
    elif head == 1:
        first = read_char(16)
    else:
        return None
    if first is None:
        return None
    dictionary.append(first)      # 占字典索引 3
    entry = first
    result.append(first)

    while True:
        if index > length:
            return ""
        code = read_bits(num_bits)
        if code is None:
            return None
        literal = None
        if code == 0:
            literal = read_char(8)
        elif code == 1:
            literal = read_char(16)
        elif code == 2:
            return "".join(result)
        if literal is not None:
            dictionary.append(literal)
            code = len(dictionary) - 1
            enlarge_in -= 1
        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1
        # 引用解析：字典已有 -> 直接取；等于下一个新码 -> entry+entry[0]
        if 0 <= code < len(dictionary) and dictionary[code] is not None:
            d = dictionary[code]
        else:
            if code != len(dictionary):
                return None
            d = entry + entry[0]
        result.append(d)
        dictionary.append(entry + d[0])
        enlarge_in -= 1
        entry = d
        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1


def decompress_base64(text):
    """解压 lz-string 的 Base64 存档串；失败返回 None。"""
    if not text:
        return None
    try:
        return _decompress(len(text), 32,
                           lambda i: _B64_REVERSE.get(text[i], 64))
    except Exception:
        return None


def decompress_utf16(text):
    """解压 lz-string 的 UTF16 存档串；失败返回 None。"""
    if not text:
        return None
    try:
        return _decompress(len(text), 16384,
                           lambda i: ord(text[i]) - 32)
    except Exception:
        return None


def _compress_base64_units(text):
    """移植 LZString._compress 的 Base64 变体（6 位/符号）的位打包。

    语义要点（对照 lz-string 源码）：
    - 字面量写出时 enlarge_in 递减两次，引用写出时递减一次；
    - 编码按 LSB 优先逐位写入；
    - 结束码为 2，最后补零填满一个 6 位符号。
    """
    dictionary = {}      # 片段 -> 编码
    first_use = {}       # 单字符首次出现（尚未按字面量写出）
    context = ""
    enlarge_in = 2
    next_code = 3
    num_bits = 2
    out = []
    d = 0
    S = 0
    e = 6
    grow_count = 0       # 本次 flush 待补的 enlarge 递减次数

    def add_bit(bit):
        nonlocal d, S
        d = (d << 1) | (1 if bit else 0)
        if S == e - 1:
            out.append(d)
            d = 0
            S = 0
        else:
            S += 1

    def add_value(value, bits):
        t = value
        for _ in range(bits):
            add_bit(t & 1)
            t >>= 1

    def grow():
        nonlocal enlarge_in, num_bits
        enlarge_in -= 1
        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1

    def write_literal(ch):
        code = ord(ch)
        if code < 256:
            add_value(0, num_bits)
            add_value(code, 8)
        else:
            add_value(1, num_bits)
            add_value(code, 16)
        nonlocal grow_count
        grow_count += 2          # 字面量：对照源码递减两次
        first_use.pop(ch, None)

    def write_reference(code):
        add_value(code, num_bits)
        nonlocal grow_count
        grow_count += 1          # 引用：递减一次

    def flush(is_tail):
        nonlocal context, grow_count
        if not context:
            return
        grow_count = 0
        if context in first_use:
            write_literal(context)
        else:
            write_reference(dictionary[context])
        for _ in range(grow_count):
            grow()
        if is_tail:
            context = ""
        else:
            context = ""          # 调用方随后会重建上下文

    for ch in text:
        if ch not in dictionary:
            dictionary[ch] = next_code
            next_code += 1
            first_use[ch] = True
        pair = context + ch
        if pair in dictionary:
            context = pair
            continue
        if context:
            flush(False)
            dictionary[pair] = next_code
            next_code += 1
        context = ch

    if context:
        flush(True)

    # 结束码 2
    add_value(2, num_bits)
    # 补足最后一个 6 位符号
    while True:
        d <<= 1
        if S == e - 1:
            out.append(d)
            break
        S += 1
    return out


def compress_base64(text):
    """把存档 JSON 文本压缩为 lz-string Base64 字符串（含 = 补位）。"""
    units = _compress_base64_units(text)
    res = "".join(_B64_ALPHABET[u] for u in units)
    rest = len(res) % 4
    if rest == 1:
        res += "==="
    elif rest == 2:
        res += "=="
    elif rest == 3:
        res += "="
    return res


def validate(text):
    """校验存档文本。

    :return: (ok, kind)
        ok=True 表示疑似合法存档（原始 JSON / base64 / utf16 任一可解码为 JSON）
        kind ∈ {'json','base64','utf16', None}
    """
    if not text or not text.strip():
        return False, None
    data = text.strip()
    try:
        if data[0] == "{":
            json.loads(data)
            return True, "json"
    except Exception:
        pass
    out = decompress_base64(data)
    if out:
        try:
            if out[0] == "{" and json.loads(out):
                return True, "base64"
        except Exception:
            pass
    out = decompress_utf16(data)
    if out:
        try:
            if out[0] == "{" and json.loads(out):
                return True, "utf16"
        except Exception:
            pass
    return False, None
