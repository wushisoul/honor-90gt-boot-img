"""远程 ZIP 读取器：只靠 HTTP Range 取中央目录，按需单独取某个成员。

用法:
  python remote_zip.py list <url>
  python remote_zip.py get  <url> <成员名> <输出文件>
"""

import binascii
import struct
import sys
import urllib.request
import zlib

UA = {"User-Agent": "Mozilla/5.0"}


def req(url, rng=None, method="GET"):
    r = urllib.request.Request(url, headers=dict(UA), method=method)
    if rng:
        r.add_header("Range", "bytes=%d-%d" % rng)
    return urllib.request.urlopen(r, timeout=60)


def size_of(url):
    try:
        with req(url, method="HEAD") as r:
            n = r.headers.get("Content-Length")
            if n:
                return int(n)
    except Exception:
        pass
    with req(url, (0, 0)) as r:
        cr = r.headers.get("Content-Range", "")
        if "/" in cr:
            return int(cr.split("/")[-1])
        raise RuntimeError("cannot determine size")


def get_range(url, start, length):
    with req(url, (start, start + length - 1)) as r:
        return r.read()


def parse_eocd(url):
    total = size_of(url)
    tail_len = 65536
    tail_start = max(0, total - tail_len)
    tail = get_range(url, tail_start, min(tail_len, total))

    idx = tail.rfind(b"PK\x05\x06")
    if idx < 0:
        raise RuntimeError("EOCD not found")
    eocd = tail[idx:idx + 22]
    (_, _, _, entries16, _, cd_size32, cd_off32, _) = struct.unpack("<IHHHHIIH", eocd)

    if entries16 == 0xFFFF or cd_off32 == 0xFFFFFFFF or cd_size32 == 0xFFFFFFFF:
        loc = tail.rfind(b"PK\x06\x07")
        if loc < 0:
            raise RuntimeError("zip64 locator not found")
        z64_off = struct.unpack("<Q", tail[loc + 8:loc + 16])[0]
        rec = get_range(url, z64_off, 56)
        if rec[:4] != b"PK\x06\x06":
            raise RuntimeError("bad zip64 eocd")
        entries64, cd_size64, cd_off64 = struct.unpack("<QQQ", rec[32:56])
        return total, entries64, cd_size64, cd_off64
    return total, entries16, cd_size32, cd_off32


def central_directory(url):
    total, n, cd_size, cd_off = parse_eocd(url)
    cd = get_range(url, cd_off, cd_size)
    out = []
    p = 0
    while p < len(cd) and cd[p:p + 4] == b"PK\x01\x02":
        (ver, verneed, flag, method, mtime, mdate, crc, csize, usize,
         nlen, elen, clen, _, _, _, lho) = struct.unpack("<HHHHHHIIIHHHHHII", cd[p + 4:p + 46])
        name = cd[p + 46:p + 46 + nlen].decode("utf-8", "replace")
        extra = cd[p + 46 + nlen:p + 46 + nlen + elen]
        if csize == 0xFFFFFFFF or usize == 0xFFFFFFFF or lho == 0xFFFFFFFF:
            q = 0
            while q + 4 <= len(extra):
                hid, hsz = struct.unpack("<HH", extra[q:q + 4])
                if hid == 0x0001:
                    vals = extra[q + 4:q + 4 + hsz]
                    k = 0
                    if usize == 0xFFFFFFFF:
                        usize = struct.unpack("<Q", vals[k:k + 8])[0]; k += 8
                    if csize == 0xFFFFFFFF:
                        csize = struct.unpack("<Q", vals[k:k + 8])[0]; k += 8
                    if lho == 0xFFFFFFFF:
                        lho = struct.unpack("<Q", vals[k:k + 8])[0]; k += 8
                    break
                q += 4 + hsz
        out.append({"name": name, "method": method, "csize": csize, "usize": usize,
                    "lho": lho, "crc": crc})
        p += 46 + nlen + elen + clen
    return total, out


def extract(url, member, dest):
    total, entries = central_directory(url)
    ent = next((e for e in entries if e["name"].strip("/") == member.strip("/")), None)
    if not ent:
        raise RuntimeError("member not found: %s" % member)
    hdr = get_range(url, ent["lho"], 30)
    nlen, elen = struct.unpack("<HH", hdr[26:30])
    data_off = ent["lho"] + 30 + nlen + elen
    raw = get_range(url, data_off, ent["csize"])
    if ent["method"] == 0:
        data = raw
    elif ent["method"] == 8:
        data = zlib.decompressobj(-15).decompress(raw)
    else:
        raise RuntimeError("unsupported method %d" % ent["method"])
    open(dest, "wb").write(data)
    print("extracted %s -> %s (%d bytes, crc32 ok=%s)" %
          (member, dest, len(data), hex(binascii.crc32(data) & 0xFFFFFFFF) == hex(ent["crc"])))
    return dest


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "list":
        total, entries = central_directory(sys.argv[2])
        print("remote size: %d bytes (%.2f GB)" % (total, total / 1024.0 ** 3))
        print("entries: %d" % len(entries))
        for e in entries:
            print("  %-46s %12d  method=%d" % (e["name"], e["usize"], e["method"]))
    elif cmd == "get":
        extract(sys.argv[2], sys.argv[3], sys.argv[4])
