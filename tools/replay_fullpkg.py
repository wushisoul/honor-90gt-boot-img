"""在检查请求里打开「全量包查询」开关，尝试拿到当前版本的全量包地址。"""

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
        URL, data=json.dumps(body, separators=(",", ":")).encode(), method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "x-devModel": "MAG-AN00",
                 "x-deviceDescId": SERIAL, "x-requestId": str(uuid.uuid4()),
                 "x-productId": "SmartPhone", "User-Agent": "hnouc/17.0.33.110"})
    try:
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            data = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        data = "HTTP%s" % e.code
    except Exception as e:
        data = "ERR%s" % type(e).__name__
    try:
        code = json.loads(data).get("errCode", "?")
    except Exception:
        code = data[:20]
    urls = sorted(set(re.findall(r"https?://[^\"' ,}]+", data)))
    print("[%-26s] errCode=%-10s urls=%d" % (tag, code, len(urls)))
    for u in urls[:8]:
        print("     " + u)
    if urls:
        open("resp_full_%s.json" % tag, "w", encoding="utf-8").write(data)
    elif len(data) > 60:
        print("     body: " + data[:180].replace("\n", " "))
    return urls


variants = []

b = copy.deepcopy(base)
b["commonRules"]["isNeedQueryDataFullPackage"] = True
variants.append((b, "flag_isNeedQuery"))

b = copy.deepcopy(base)
b["commonRules"]["needQueryDataFullPackage"] = True
variants.append((b, "flag_needQuery"))

b = copy.deepcopy(base)
b["commonRules"]["isNeedQueryDataFullPackage"] = True
b["versionPackageRules"].append({"versionPackageType": 8, "versionNumber": ""})
variants.append((b, "flag_plus_type8"))

b = copy.deepcopy(base)
b["commonRules"]["isNeedQueryDataFullPackage"] = True
b["commonRules"]["isSupportWifiQuery"] = True
b["versionPackageRules"].append({"versionPackageType": 8, "versionNumber": ""})
b["versionPackageRules"].append({"versionPackageType": 10, "versionNumber": ""})
variants.append((b, "flag_wifi_type8_10"))

allurls = []
for body, tag in variants:
    allurls += post(body, tag)
print("\nTOTAL:", len(set(allurls)))
