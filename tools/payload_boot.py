"""从远程 A/B OTA 包里只取 boot 分区，落地成 boot.img。

原理：update_full_base.zip 内是 payload.bin（CrAU 格式）。payload 头部带一份
DeltaArchiveManifest（protobuf），其中 partitions[].operations[] 给出了每个分区的
数据块在 payload.bin 里的偏移与长度。只 Range 取 boot 分区那几块，解压拼接即可，
无需下载 8 GB 整包。

用法:
  python payload_boot.py <zip_url> <zip内偏移> <输出img> [分区名]
例:
  python payload_boot.py http://.../update_full_base.zip 828 boot.img
"""

import bz2
import lzma
import os
import struct
import subprocess
import sys

BLOCK = 4096
UA = "Mozilla/5.0"


def rng(url, start, length):
    """HTTP Range 取一段，返回 bytes。"""
    out = subprocess.run(
        ["curl", "-s", "-m", "180", "-r", "%d-%d" % (start, start + length - 1), url],
        capture_output=True)
    data = out.stdout
    if len(data) != length:
        raise RuntimeError("short read: want %d got %d at %d" % (length, len(data), start))
    return data


def varint(buf, i):
    shift = 0
    val = 0
    while True:
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7


def pb_fields(buf):
    """极简 protobuf 解析：返回 [(field_no, wire_type, value)]。"""
    out = []
    i = 0
    n = len(buf)
    while i < n:
        try:
            key, i = varint(buf, i)
        except IndexError:
            break
        fno, wt = key >> 3, key & 7
        if wt == 0:
            v, i = varint(buf, i)
        elif wt == 2:
            ln, i = varint(buf, i)
            v = buf[i:i + ln]
            i += ln
        elif wt == 5:
            v = buf[i:i + 4]
            i += 4
        elif wt == 1:
            v = buf[i:i + 8]
            i += 8
        else:
            break
        out.append((fno, wt, v))
    return out


def as_msg(v):
    return pb_fields(v) if isinstance(v, (bytes, bytearray)) else []


def get_first(fields, fno, default=None):
    for f, _, v in fields:
        if f == fno:
            return v
    return default


def get_all(fields, fno):
    return [v for f, _, v in fields if f == fno]


def main():
    url, zip_off, out_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    target = sys.argv[4] if len(sys.argv) > 4 else "boot"

    head = rng(url, zip_off, 4 << 20)
    if head[:4] != b"CrAU":
        raise SystemExit("not a CrAU payload at offset %d (got %r)" % (zip_off, head[:4]))
    version = struct.unpack(">Q", head[4:12])[0]
    manifest_size = struct.unpack(">Q", head[12:20])[0]
    hdr = 20
    meta_sig = 0
    if version > 1:
        meta_sig = struct.unpack(">I", head[20:24])[0]
        hdr = 24
    print("payload version=%d manifest=%d meta_sig=%d" % (version, manifest_size, meta_sig))

    if manifest_size + hdr > len(head):
        head = rng(url, zip_off, hdr + manifest_size + meta_sig + 64)
    manifest = head[hdr:hdr + manifest_size]
    data_base = hdr + manifest_size + meta_sig
    print("manifest ok (%d bytes), data base in payload = %d" % (len(manifest), data_base))

    mf = pb_fields(manifest)
    parts = [as_msg(p) for p in get_all(mf, 13)]
    print("partitions: %d" % len(parts))

    found = None
    for p in parts:
        name = get_first(p, 1)
        if isinstance(name, bytes):
            name = name.decode("utf-8", "replace")
        if name == target:
            found = p
            break
    if not found:
        names = []
        for p in parts:
            nm = get_first(p, 1)
            if isinstance(nm, bytes):
                names.append(nm.decode("utf-8", "replace"))
        raise SystemExit("partition %r not found; have: %s" % (target, names))

    ops = [as_msg(o) for o in get_all(found, 8)]
    print("partition %s: %d operations" % (target, len(ops)))

    chunks = {}
    total = 0
    for o in ops:
        otype = get_first(o, 1, 0)
        doff = get_first(o, 2, 0)
        dlen = get_first(o, 3, 0)
        extents = [as_msg(e) for e in get_all(o, 6)]
        dst = []
        for e in extents:
            st = get_first(e, 1, 0)
            nb = get_first(e, 2, 0)
            dst.append((st, nb))
            total += nb * BLOCK
        if otype in (0, 1, 8) and dlen:
            blk = rng(url, zip_off + data_base + doff, dlen)
            if otype == 1:
                blk = bz2.decompress(blk)
            elif otype == 8:
                blk = lzma.decompress(blk)
            off = 0
            for st, nb in dst:
                size = nb * BLOCK
                chunks[st] = blk[off:off + size]
                off += size
        elif otype == 6:  # ZERO
            for st, nb in dst:
                chunks[st] = b"\x00" * (nb * BLOCK)
        else:
            print("  op type=%d skipped (needs source data)" % otype)

    img = bytearray(total)
    for st, blk in chunks.items():
        img[st * BLOCK:st * BLOCK + len(blk)] = blk
    open(out_path, "wb").write(img)
    print("wrote %s (%d bytes / %.1f MB)" % (out_path, len(img), len(img) / 1048576.0))


if __name__ == "__main__":
    main()
