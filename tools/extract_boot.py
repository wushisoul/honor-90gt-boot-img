"""从荣耀/华为官方固件包中取出 boot 镜像并校验内核版本。

支持两种输入：
  1) update.zip（A/B 全量包，内含 boot.img / boot_a.img 等）
  2) update.app（华为旧格式打包，按 0x5AA5A55A 条目扫描）

用法：
  python extract_boot.py <固件包> [输出目录]
  python extract_boot.py --verify <boot.img>          # 只解析并校验内核串
"""

import gzip
import os
import re
import struct
import sys
import zipfile

TARGET_KERNEL = "5.15.180-android13-8-g938a6e3184bd"
BOOT_MAGIC = b"ANDROID!"


def parse_boot_header(blob):
    """解析 Android boot image header，返回 dict。"""
    if len(blob) < 44 or not blob.startswith(BOOT_MAGIC):
        return None
    kernel_size, ramdisk_size, os_version = struct.unpack_from("<III", blob, 8)
    header_version = struct.unpack_from("<I", blob, 40)[0]
    info = {
        "kernel_size": kernel_size,
        "ramdisk_size": ramdisk_size,
        "os_version_raw": os_version,
        "header_version": header_version,
    }
    if header_version >= 3:
        info["header_size"] = struct.unpack_from("<I", blob, 20)[0]
        # v3/v4：内核按 4096 对齐，header 只有 1584 字节
        info["kernel_offset"] = (info["header_size"] + 4095) // 4096 * 4096
    else:
        # v0-v2：页对齐
        page = struct.unpack_from("<I", blob, 36)[0]
        info["page_size"] = page or 2048
        info["header_size"] = page
        info["kernel_offset"] = page
    return info


def kernel_blob(blob):
    """返回 (kernel_bytes, kind)。kind ∈ {raw, gz, lz4, unknown}"""
    h = parse_boot_header(blob)
    if not h:
        return None, "not-a-boot-image"
    start = h.get("kernel_offset", h["header_size"])
    k = blob[start:start + h["kernel_size"]]
    if k[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(k), "gz"
        except Exception:
            return k, "gz-truncated"
    if k[:4] == b"\x04\x22\x4d\x18":
        try:
            import lz4.frame
            return lz4.frame.decompress(k), "lz4"
        except Exception:
            return k, "lz4-unavailable"
    if k[:4] == b"\x89LZO" or k[:5] == b"\x89LZO\x00":
        return k, "lzo"
    return k, "raw"


def find_target(kdata):
    """在内核里定位目标版本串，返回偏移列表。"""
    return [m.start() for m in re.finditer(re.escape(TARGET_KERNEL.encode()), kdata)]


def report(path):
    blob = open(path, "rb").read()
    h = parse_boot_header(blob)
    print("file      : %s (%d bytes)" % (path, len(blob)))
    if not h:
        print("header    : NOT an Android boot image")
        return 1
    print("header_ver: %d" % h["header_version"])
    print("kernel    : %d bytes" % h["kernel_size"])
    print("ramdisk   : %d bytes" % h["ramdisk_size"])
    print("header_sz : %d" % h["header_size"])
    k, kind = kernel_blob(blob)
    print("kernel_fmt: %s (%d bytes after unpack)" % (kind, len(k)))
    hits = find_target(k)
    m = re.search(rb"Linux version ([^\x00\n]{20,120})", k)
    print("linux_banner: %s" % (m.group(1).decode("ascii", "replace") if m else "(not found)"))
    if hits:
        print("MATCH     : kernel string found at %s" % hits[:5])
        print("RESULT    : EXACT_MATCH")
        return 0
    print("RESULT    : MISMATCH")
    return 2


def from_zip(archive, outdir):
    got = []
    with zipfile.ZipFile(archive) as z:
        names = [n for n in z.namelist() if re.search(r"(^|/)boot(_a|_b)?\.img$", n)]
        if not names:
            print("no boot*.img in zip; entries sample:")
            for n in z.namelist()[:20]:
                print("  " + n)
            return got
        for n in names:
            dest = os.path.join(outdir, os.path.basename(os.path.dirname(n)) + "_" + os.path.basename(n)
                                if os.path.dirname(n) else os.path.basename(n))
            with z.open(n) as src, open(dest, "wb") as dst:
                dst.write(src.read())
            print("extracted %s -> %s" % (n, dest))
            got.append(dest)
    return got


def from_update_app(path, outdir):
    """扫描 0x5AA5A55A 条目，抽出镜像。"""
    got = []
    data = open(path, "rb").read()
    magic = b"\x5a\xa5\xa5\x5a"
    off = 0
    while True:
        i = data.find(magic, off)
        if i < 0:
            break
        off = i + 4
        if i + 0x6C > len(data):
            break
        _sig, ftype, _seq, fsize, foff, _crc, _res = struct.unpack_from("<7I", data, i)
        name = data[i + 28:i + 60].split(b"\x00")[0].decode("ascii", "ignore")
        if not re.match(r"^[A-Za-z0-9_.\-]{3,31}$", name or ""):
            continue
        if not (0 < fsize <= len(data)) or not (0 < foff < len(data)):
            continue
        if foff + fsize > len(data):
            continue
        if not name.lower().endswith((".img", ".bin")):
            continue
        dest = os.path.join(outdir, name)
        with open(dest, "wb") as f:
            f.write(data[foff:foff + fsize])
        print("extracted %-20s type=%d size=%d -> %s" % (name, ftype, fsize, dest))
        got.append(dest)
    return got


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    if sys.argv[1] == "--verify":
        return report(sys.argv[2])

    src = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "out_boot"
    os.makedirs(outdir, exist_ok=True)

    if zipfile.is_zipfile(src):
        got = from_zip(src, outdir)
    else:
        got = from_update_app(src, outdir)

    rc = 0
    for p in got:
        if os.path.basename(p).startswith("boot"):
            print("-" * 50)
            rc = report(p) or rc
    if not got:
        print("no boot image extracted")
        rc = 3
    return rc


if __name__ == "__main__":
    sys.exit(main())
