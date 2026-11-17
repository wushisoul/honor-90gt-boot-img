"""监听荣耀 OTA 客户端的下载地址，一旦出现新版本即落盘。

OUC 在检查更新时会打印 "getNewVersionFromServer request url: ..."，
下载固件时会打印包地址。本脚本常驻 tail logcat，把命中的 URL 追加写入
ota_urls.log，供后续用 extract_boot.py 取 boot.img。

用法：python ota_url_watch.py
停止：Ctrl+C
"""

import re
import subprocess
import sys
import time

ADB = r"D:\software\platform-tools\adb.exe"
OUT = "ota_urls.log"
TAGS = "HnOUC|HOTA_OUC|HnUpdateService|P_OUC|VAB_OUC"

PATTERNS = [
    re.compile(r"request url:\s*(\S+)"),
    re.compile(r"(https?://\S+?(?:update\.zip|\.zip|full/[^\s\"']+))"),
    re.compile(r"(?:downloadUrl|packageUrl|pkgUrl)[\"']?\s*[:=]\s*[\"']?(https?://[^\s\"',}]+)"),
]

seen = set()
proc = subprocess.Popen(
    [ADB, "logcat", "-v", "time", "-s", TAGS],
    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="ignore",
    bufsize=1,
)
print("listening on tags: %s" % TAGS, flush=True)
try:
    for line in proc.stdout:
        for p in PATTERNS:
            m = p.search(line)
            if not m:
                continue
            url = m.group(1).rstrip(")")
            if url in seen:
                continue
            seen.add(url)
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(OUT, "a", encoding="utf-8") as f:
                f.write("%s\t%s\n" % (ts, url))
            print("[%s] %s" % (ts, url), flush=True)
except KeyboardInterrupt:
    print("\nstopped")
finally:
    proc.terminate()
