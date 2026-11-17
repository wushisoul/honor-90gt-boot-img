"""回放荣耀 OTA 检查请求。

从设备日志里提取 getNewVersionFromServer 的原始请求体，补齐被掩码的设备号，
向 https://update.platform.hihonorcloud.com/blversion/v2/version/check 发起 POST。
"""

import json
import re
import ssl
import sys
import urllib.request
import uuid

LOG = "tap_log.txt"
SERIAL = "AP4XUT49XXXXXXXX"
URL = "https://update.platform.hihonorcloud.com/blversion/v2/version/check"

raw = open(LOG, encoding="utf-8", errors="ignore").read()
m = re.search(r"getNewVersionFromServer request body: (\{.*?\})\(HttpUtils", raw, re.S)
if not m:
    print("请求体未在日志中找到")
    sys.exit(1)
body_text = m.group(1)
body_text = body_text.replace("AP4XUT491900****", SERIAL)
try:
    body = json.loads(body_text)
except Exception as e:
    print("body JSON 解析失败:", e)
    print(body_text[:300])
    sys.exit(1)

print("body keys:", list(body.keys()))
print("devModel:", body.get("devModel"), "| fingerprint:", body.get("fingerPrint"))

req = urllib.request.Request(
    URL,
    data=json.dumps(body, separators=(",", ":")).encode(),
    method="POST",
    headers={
        "Content-Type": "application/json; charset=utf-8",
        "x-devModel": "MAG-AN00",
        "x-deviceDescId": SERIAL,
        "x-requestId": str(uuid.uuid4()),
        "x-productId": "SmartPhone",
        "User-Agent": "hnouc/17.0.33.110",
    },
)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
try:
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        data = r.read().decode("utf-8", "replace")
        print("HTTP", r.status)
        open("check_response.json", "w", encoding="utf-8").write(data)
        print(data[:3000])
except urllib.error.HTTPError as e:
    print("HTTPError", e.code)
    print(e.read().decode("utf-8", "replace")[:1500])
except Exception as e:
    print("ERR", type(e).__name__, e)
