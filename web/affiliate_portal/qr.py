"""Tiny dependency-free QR code encoder -> inline SVG (partner dashboard).

Byte mode, error correction level M, versions 1-13 (up to 331 bytes - enough
for a tracked link with UTM parameters). Server-side on purpose: no external
CDN, no JS library, and the SVG can be saved or printed as-is.

    matrix(data) -> list[list[bool]]      (True = dark module)
    svg(data, scale=6, border=4) -> str   (a complete <svg> document)

Raises ValueError when the data does not fit version 13.
"""

# version -> (ec codewords per block, [(blocks, data codewords per block), ...])
_BLOCKS_M = {
    1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]),
    5: (24, [(2, 43)]), 6: (16, [(4, 27)]), 7: (18, [(4, 31)]),
    8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
    10: (26, [(4, 43), (1, 44)]), 11: (30, [(1, 50), (4, 51)]),
    12: (22, [(6, 36), (2, 37)]), 13: (22, [(8, 37), (1, 38)]),
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
          7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
          11: [6, 30, 54], 12: [6, 32, 58], 13: [6, 34, 62]}
MAX_VERSION = max(_BLOCKS_M)

# GF(256) tables, primitive polynomial 0x11D
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _rs_generator(n):
    g = [1]
    for i in range(n):
        nxt = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            nxt[j] ^= c
            if c:
                nxt[j + 1] ^= _EXP[_LOG[c] + i]
        g = nxt
    return g


def _rs_remainder(data, n):
    gen = _rs_generator(n)
    rem = [0] * n
    for b in data:
        factor = b ^ rem[0]
        rem = rem[1:] + [0]
        if factor:
            lf = _LOG[factor]
            for i in range(n):
                if gen[i + 1]:
                    rem[i] ^= _EXP[_LOG[gen[i + 1]] + lf]
    return rem


def _capacity(version):
    ec, groups = _BLOCKS_M[version]
    return sum(n * size for n, size in groups)


def _pick_version(nbytes):
    for v in range(1, MAX_VERSION + 1):
        header_bits = 4 + (8 if v < 10 else 16)
        if header_bits + 8 * nbytes <= 8 * _capacity(v):
            return v
    raise ValueError("data too long for a QR code (max %d bytes)" % (_capacity(MAX_VERSION) - 3))


def _codewords(payload, version):
    bits = []

    def put(value, n):
        for i in range(n - 1, -1, -1):
            bits.append((value >> i) & 1)

    put(0b0100, 4)                                  # byte mode
    put(len(payload), 8 if version < 10 else 16)
    for b in payload:
        put(b, 8)
    cap_bits = 8 * _capacity(version)
    put(0, min(4, cap_bits - len(bits)))            # terminator
    while len(bits) % 8:
        bits.append(0)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = (0xEC, 0x11)
    i = 0
    while len(data) < cap_bits // 8:
        data.append(pad[i % 2])
        i += 1

    ec_len, groups = _BLOCKS_M[version]
    blocks, pos = [], 0
    for count, size in groups:
        for _ in range(count):
            blocks.append(data[pos:pos + size])
            pos += size
    ec_blocks = [_rs_remainder(b, ec_len) for b in blocks]
    out = []
    for i in range(max(len(b) for b in blocks)):
        out.extend(b[i] for b in blocks if i < len(b))
    for i in range(ec_len):
        out.extend(b[i] for b in ec_blocks)
    return out


def _bch(value, poly, total_bits, data_shift):
    rem = value << data_shift
    plen = poly.bit_length()
    for i in range(total_bits - 1, data_shift - 1, -1):
        if rem & (1 << i):
            rem ^= poly << (i - (plen - 1))
    return (value << data_shift) | rem


_MASKS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]


def _base(version):
    n = 17 + 4 * version
    mod = [[False] * n for _ in range(n)]
    fn = [[False] * n for _ in range(n)]        # function-module map

    def setf(r, c, dark):
        if 0 <= r < n and 0 <= c < n:
            mod[r][c] = dark
            fn[r][c] = True

    def finder(r0, c0):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                inside = 0 <= dr <= 6 and 0 <= dc <= 6
                dark = inside and (dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4))
                setf(r0 + dr, c0 + dc, dark)

    finder(0, 0)
    finder(0, n - 7)
    finder(n - 7, 0)
    for i in range(8, n - 8):                    # timing
        setf(6, i, i % 2 == 0)
        setf(i, 6, i % 2 == 0)
    pos = _ALIGN[version]
    for r in pos:
        for c in pos:
            if (r, c) in ((6, 6), (6, pos[-1]), (pos[-1], 6)):
                continue                         # overlaps a finder
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    setf(r + dr, c + dc, max(abs(dr), abs(dc)) != 1)
    for i in range(9):                           # reserve format areas
        if not fn[8][i]:
            setf(8, i, False)
        if not fn[i][8]:
            setf(i, 8, False)
    for i in range(8):
        setf(8, n - 1 - i, False)
        setf(n - 1 - i, 8, False)
    setf(n - 8, 8, True)                         # dark module
    if version >= 7:
        info = _bch(version, 0x1F25, 18, 12)
        for i in range(18):
            bit = bool((info >> i) & 1)
            a, b = i // 3, n - 11 + i % 3
            setf(a, b, bit)
            setf(b, a, bit)
    return n, mod, fn


def _place(n, mod, fn, codewords):
    bits = []
    for cw in codewords:
        for i in range(7, -1, -1):
            bits.append((cw >> i) & 1)
    idx = 0
    col = n - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(n - 1, -1, -1) if upward else range(n)
        for r in rows:
            for c in (col, col - 1):
                if not fn[r][c]:
                    mod[r][c] = bool(bits[idx]) if idx < len(bits) else False
                    idx += 1
        upward = not upward
        col -= 2


def _apply_format(n, mod, mask):
    info = _bch((0b00 << 3) | mask, 0x537, 15, 10) ^ 0x5412     # level M = 00
    for i in range(15):
        bit = bool((info >> i) & 1)
        # copy 1 (around the top-left finder)
        if i < 6:
            mod[i][8] = bit
        elif i < 8:
            mod[i + 1][8] = bit
        elif i == 8:
            mod[8][7] = bit
        else:
            mod[8][14 - i] = bit
        # copy 2 (split between top-right and bottom-left)
        if i < 8:
            mod[8][n - 1 - i] = bit
        else:
            mod[n - 15 + i][8] = bit


def _penalty(n, m):
    score = 0
    lines = [row for row in m] + [[m[r][c] for r in range(n)] for c in range(n)]
    pat1 = [True, False, True, True, True, False, True, False, False, False, False]
    pat2 = pat1[::-1]
    for line in lines:
        run, prev = 1, line[0]
        for v in line[1:]:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run, prev = 1, v
        if run >= 5:
            score += run - 2
        for i in range(n - 10):
            seg = line[i:i + 11]
            if seg == pat1 or seg == pat2:
                score += 40
    for r in range(n - 1):
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    dark = sum(sum(1 for v in row if v) for row in m)
    score += (abs(dark * 20 - n * n * 10) // (n * n)) * 10
    return score


def matrix(data, mask=None):
    """The QR module matrix for `data` (str -> UTF-8, or bytes)."""
    payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    version = _pick_version(len(payload))
    codewords = _codewords(payload, version)
    n, base, fn = _base(version)
    _place(n, base, fn, codewords)
    best = None
    for k in ([mask] if mask is not None else range(8)):
        m = [row[:] for row in base]
        f = _MASKS[k]
        for r in range(n):
            for c in range(n):
                if not fn[r][c] and f(r, c):
                    m[r][c] = not m[r][c]
        _apply_format(n, m, k)
        p = _penalty(n, m)
        if best is None or p < best[0]:
            best = (p, m)
    return best[1]


def svg(data, scale=6, border=4, dark="#000000", light="#ffffff"):
    """A complete SVG document (white quiet zone included, crisp edges)."""
    m = matrix(data)
    n = len(m)
    size = (n + 2 * border) * scale
    parts = []
    for r, row in enumerate(m):
        c = 0
        while c < n:
            if row[c]:
                start = c
                while c < n and row[c]:
                    c += 1
                parts.append("M%d %dh%dv1h-%dz" % (start + border, r + border, c - start, c - start))
            else:
                c += 1
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
            'shape-rendering="crispEdges" role="img" aria-label="QR code">'
            '<rect width="100%%" height="100%%" fill="%s"/><path fill="%s" d="%s"/></svg>'
            % (size, size, n + 2 * border, n + 2 * border, light, dark, "".join(parts)))
