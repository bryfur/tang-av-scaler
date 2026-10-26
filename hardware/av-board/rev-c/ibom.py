"""Decode an InteractiveHtmlBom page's pcbdata (LZString base64): python3 ibom.py page.html out.json"""
import json, re, sys

KEY = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="


def lz_decompress_b64(s):
    rev = {c: i for i, c in enumerate(KEY)}
    data = [rev[c] for c in s if c in rev]
    pos, val, idx = 32, data[0], 1
    reset = 32

    def bits(n):
        nonlocal pos, val, idx
        r, p = 0, 1
        for _ in range(n):
            b = val & pos
            pos >>= 1
            if pos == 0:
                pos = reset
                val = data[idx] if idx < len(data) else 0
                idx += 1
            r |= (1 if b else 0) * p
            p <<= 1
        return r
    d = {0: 0, 1: 1, 2: 2}
    enlarge, dsize, nbits = 4, 4, 3
    c = bits(2)
    if c == 0:
        w = chr(bits(8))
    elif c == 1:
        w = chr(bits(16))
    else:
        return ""
    d[3] = w
    out = [w]
    while True:
        c = bits(nbits)
        if c == 0:
            d[dsize] = chr(bits(8)); dsize += 1; c = dsize - 1; enlarge -= 1
        elif c == 1:
            d[dsize] = chr(bits(16)); dsize += 1; c = dsize - 1; enlarge -= 1
        elif c == 2:
            return "".join(out)
        if enlarge == 0:
            enlarge = 1 << nbits; nbits += 1
        if c in d:
            entry = d[c]
        elif c == dsize:
            entry = w + w[0]
        else:
            return None
        out.append(entry)
        d[dsize] = w + entry[0]; dsize += 1
        enlarge -= 1
        w = entry
        if enlarge == 0:
            enlarge = 1 << nbits; nbits += 1


if __name__ == "__main__":
    src = open(sys.argv[1]).read()
    m = re.search(r'LZString\.decompressFromBase64\("([^"]+)"\)', src)
    json.dump(json.loads(lz_decompress_b64(m.group(1))), open(sys.argv[2], "w"))
