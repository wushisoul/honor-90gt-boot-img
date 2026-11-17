"""抓取荣耀 OTA 客户端的真实下载主机与 URL。

原理：OUC 走系统全局 HTTP 代理（已实测会发 CONNECT），代理在明文 CONNECT 行里
暴露被日志掩码成 **** 的真实主机名，随后用该主机取 v877311 的 changelog，
changelog XML 内含全量包 URL（含包组号 G<num>）。

用法：python ota_hunt.py <PC_IP> [PORT]
"""

import re
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

ADB = r"D:\software\platform-tools\adb.exe"
PKG = "com.hihonor.ouc"
ACT = "com.hihonor.ouc/com.hihonor.android.hnouc.ui.activities.MainEntranceActivity"

PC_IP = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8899


def adb(*args, timeout=25):
    return subprocess.run([ADB] + list(args), capture_output=True, text=True,
                          timeout=timeout, errors="ignore")


hits = []
stop = threading.Event()


def serve():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(100)
    srv.settimeout(1.0)
    while not stop.is_set():
        try:
            c, _ = srv.accept()
        except socket.timeout:
            continue
        try:
            c.settimeout(3)
            d = c.recv(8192)
            line = d.split(b"\r\n")[0].decode("latin1").strip()
            if line:
                hits.append(line)
                print("REQ %s" % line, flush=True)
            c.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        except Exception:
            pass
        finally:
            try:
                c.close()
            except Exception:
                pass
    srv.close()


def tap_check_update():
    """在 OUC 界面里找到「检查更新」并点击。"""
    adb("shell", "am", "force-stop", PKG)
    adb("shell", "am", "start", "-n", ACT)
    time.sleep(3)
    out = adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    adb("pull", "/sdcard/ui.xml", "mag-an00/ui.xml")
    text = ""
    try:
        text = open("mag-an00/ui.xml", encoding="utf-8", errors="ignore").read()
    except Exception:
        return False, "ui dump failed: %s" % out.stderr[:200]
    want = ["检查更新", "檢查更新", "检测新版本", "立即检查", "升级尝鲜"]
    for node in ET.fromstring(text).iter("node"):
        label = (node.get("text") or "") + "|" + (node.get("content-desc") or "")
        if any(w in label for w in want):
            b = node.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
            if not m:
                continue
            x = (int(m.group(1)) + int(m.group(3))) // 2
            y = (int(m.group(2)) + int(m.group(4))) // 2
            adb("shell", "input", "tap", str(x), str(y))
            return True, "tapped %s at %d,%d" % (label.split("|")[0], x, y)
    return False, "no update button in ui"


def main():
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    time.sleep(0.5)
    print("proxy listening on %s:%d" % (PC_IP, PORT), flush=True)

    adb("shell", "settings", "put", "global", "http_proxy", "%s:%d" % (PC_IP, PORT))
    ok, msg = tap_check_update()
    print("tap: %s | %s" % (ok, msg), flush=True)

    deadline = time.time() + 45
    while time.time() < deadline:
        time.sleep(1)
    stop.set()
    time.sleep(1)
    adb("shell", "settings", "put", "global", "http_proxy", ":0")

    print("\n=== captured %d requests ===" % len(hits))
    hosts = set()
    for h in hits:
        m = re.search(r"(?:CONNECT\s+|https?://)([A-Za-z0-9._-]+)", h)
        if m:
            hosts.add(m.group(1))
    for h in sorted(hosts):
        print("HOST", h)


if __name__ == "__main__":
    main()
