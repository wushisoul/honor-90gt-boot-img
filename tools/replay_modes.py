"""试探 OTA 检查接口的 repair/recover 模式，索取当前构建的全量包。"""

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


def post(body, tag):
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
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            data = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        data = "HTTPError %s" % e.code
    except Exception as e:
        data = "ERR %s %s" % (type(e).__name__, e)

    try:
        j = json.loads(data)
        code = j.get("errCode", "")
        keys = list(j.get("result", {}).keys()) if isinstance(j.get("result"), dict) else []
    except Exception:
        code, keys = "?", []
    urls = sorted(set(re.findall(r"https?://[^\"' ,}]+", data)))
    print("[%-22s] errCode=%-10s result_keys=%s urls=%d" % (tag, code, keys, len(urls)))
    for u in urls[:10]:
        print("     " + u)
    if urls:
        open("resp_%s.json" % tag, "w", encoding="utf-8").write(data)
    return urls


V = []
b = copy.deepcopy(base); b["commonRules"]["checkMode"] = "REPAIR"; V.append((b, "checkMode_REPAIR"))
b = copy.deepcopy(base); b["commonRules"]["checkMode"] = "repair"; V.append((b, "checkMode_lower"))
b = copy.deepcopy(base); b["commonRules"]["updateAction"] = "recover"; V.append((b, "action_recover"))
b = copy.deepcopy(base); b["commonRules"]["updateAction"] = "repair"; V.append((b, "action_repair"))
b = copy.deepcopy(base); b["commonRules"]["updateType"] = 9; V.append((b, "updateType_9"))
b = copy.deepcopy(base); b["commonRules"]["checkMode"] = "DOWNGRADE"; V.append((b, "checkMode_DOWNGRADE"))

hits = []
for body, tag in V:
    hits += post(body, tag)

print("\nTOTAL urls:", len(set(hits)))
