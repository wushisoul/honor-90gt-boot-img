"""枚举检查接口的 updateAction/updateType 组合，寻找返回全量包地址的取值。"""

import copy
import json
import re
import ssl
import urllib.error
import urllib.request
import uuid

LOG = "tap_log.txt"
SERIAL = "AP4XUT49XXXXXXXX"
URL = "https://update.platform.hihonorcloud.com/blversion/v2/version/check"

raw = open(LOG, encoding="utf-8", errors="ignore").read()
m = re.search(r"getNewVersionFromServer request body: (\{.*?\})\(HttpUtils", raw, re.S)
base = json.loads(m.group(1).replace("AP4XUT491900****", SERIAL))

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def post(body):
    req = urllib.request.Request(
        URL, data=json.dumps(body, separators=(",", ":")).encode(), method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "x-devModel": "MAG-AN00",
                 "x-deviceDescId": SERIAL, "x-requestId": str(uuid.uuid4()),
                 "x-productId": "SmartPhone", "User-Agent": "hnouc/17.0.33.110"})
    try:
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return "HTTP%s" % e.code
    except Exception as e:
        return "ERR%s" % type(e).__name__


actions = ["upgrade", "full", "fullPackage", "download", "recover", "recoverFull",
           "forceUpgrade", "verify", "repair"]
types = [1, 2, 3]
seen = {}
for a in actions:
    for t in types:
        b = copy.deepcopy(base)
        b["commonRules"]["updateAction"] = a
        b["commonRules"]["updateType"] = t
        data = post(b)
        code = "?"
        try:
            code = json.loads(data).get("errCode", "?")
        except Exception:
            code = data[:20]
        urls = re.findall(r"https?://[^\"' ,}]+", data)
        key = (code, len(urls))
        if key not in seen:
            seen[key] = (a, t, data)
            print("%-14s type=%d -> errCode=%s urls=%d" % (a, t, code, len(urls)))
        if urls:
            print("  URLS:")
            for u in sorted(set(urls)):
                print("   " + u)
            open("resp_hit_%s_%d.json" % (a, t), "w", encoding="utf-8").write(data)
print("\n不同响应种类:", len(seen))
