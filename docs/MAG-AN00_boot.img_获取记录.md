# 荣耀 90 GT（MAG-AN00）原厂 boot.img 获取全记录

> 目标：内核 `5.15.180-android13-8-g938a6e3184bd`（构建 2026-08-07 09:10:03 UTC）对应的 `boot.img`
> 设备：MAG-AN00 / 荣耀 90 GT / SM8550 / 系统 `MAG-AN00 10.0.0.175(C00E170R8P1)` / Android 16 + MagicOS 10
> 结果：**已取得**，来自官方 OTA 全量包，内核串精确匹配

---

## 0. 一句话结论

官方固件里确实有 `boot.img`，但它不在任何公开下载页上，也不在 OTA「检查更新」接口的返回里。
真正的入口是**荣耀手机助理「系统修复」流程所用的 `onestopCheck.action` 接口**——它会返回
`recovery` 目标组件的 `versionId`，再由 CDN 的 `filelist.xml` 定位到 8.09 GB 的全量包。
最后用 HTTP Range 只取 boot 分区，实际传输约 100 MB。

---

## 1. 设备侧为什么拿不到

| 手段 | 实测 | 结论 |
|---|---|---|
| `adb shell dd if=/dev/block/sde33`（boot_a） | 分区权限 `brw------- root root`，输出 **0 字节** | shell(uid 2000) 不可读 |
| `adb root` | `ro.debuggable=0`、`ro.build.type=user` | 不可用 |
| `fastboot fetch boot_a` | `ro.boot.flash.locked=1`、`verifiedbootstate=green` | 锁 BL，必被拒 |
| Windows 侧 fastboot 绑定 | 设备 PID `USB\VID_18D1&PID_D00D`，Google `android_winusb.inf` 内检索 `D00D` **0 条命中** | 装驱动也无法绑定，且即使绑定也不能读分区 |
| OUC 的 ContentProvider（`versioninfodb`、`hwcota_download`） | `SecurityException: requires hihonor.android.permission.HW_SIGNATURE_OR_SYSTEM` | 非 root 不可查 |

> 结论：**唯一可行来源是官方 OTA 包**，且必须与当前构建同版本。

---

## 2. 服务端接口：能查到什么、查不到什么

### 2.1 手机端使用的检查接口

```
POST https://update.platform.hihonorcloud.com/blversion/v2/version/check
POST https://update.platform.hihonorcloud.com/blversion/v1/version/check    （PC 套件用 v1）
GET  https://update.platform.hihonorcloud.com/blversion/v1/version/authorize
```

请求头：`x-devModel` / `x-deviceDescId` / `x-requestId` / `x-productId`
请求体（节选，来自设备 logcat 原文）：

```json
{"commonRules":{"platformVersion":"10.0.0","devModel":"MAG-AN00",
 "fingerPrint":"HONOR/MAG-AN00/HNMAG:16/HONORMAG-AN00/10DLDLD175C00E170:user/release-keys",
 "updateAction":"upgrade","updateType":1,"clientType":"hnouc","clientVersion":"170033110",
 "hotaBlVersion":"MAG-AN00 10.0.0.175(C00E170R8P1)"},
 "versionPackageRules":[{"versionPackageType":2,"versionNumber":"MAG-LGRP1-CHN 10.0.0.175"}, ...],
 "deviceInfo":{"deviceId":"AP4XUT49XXXXXXXX","udid":"..."}}
```

**对已是最新版本的设备，该接口恒定返回：**

```json
{"errCode":"101003404","errMsg":"ota packageInfo is not exist",
 "result":{"cotaInfo":{"country":"UNKNOWN","vendorCota":"UNKNOWN"}, ...}}
```

即：**它只服务「升级」，永远不返回当前版本的全量包**。
把 `updateAction` 换成 `full / recover / repair`、把版本号改成旧版本、补 `plmn=46000`、
追加 `isNeedQueryDataFullPackage=true`，共 30 余种组合全部同码。
根因是设备 attestation 字段（`usageInfo`、`plmn`、`udid`）在 logcat 中被掩码，PC 回放无法通过校验，
`cotaInfo.country` 始终为 `UNKNOWN`。

### 2.2 真正的入口：PC 套件的 onestopCheck

安装**荣耀手机助理**（官方 `service.hihonor.com/weknow/servlet/download/public?contextNo=W00066135`，
V11.0.0.736）后，其安装目录的 GRS 路由表
`grs/router/grs_app_global_route_config.json` 明确写出：

```json
{"name":"com.hihonor.cloud.hotaUnique",
 "servings":[{"countryOrAreaGroup":"DR1","addresses":{
   "ROOT":"https://update.platform.hihonorcloud.com",
   "BLROOT":"https://update.platform.hihonorcloud.com"}}]}
```

而 `HonorSuite.exe` 内可见端点字符串：

```
/blversion/v1/version/authorize
/blversion/v1/version/check
```

套件「系统修复」走的是另一条接口：

```
https://update.platform.hihonorcloud.com/sp_ard_common/v2/onestopCheck.action?latest=true
```

**突破口就在套件日志里。** 路径：

```
%LOCALAPPDATA%\HonorSuite\log\SystemUpdate_YYYYMMDD_00.log
```

其中 `recovery bl_result body=` 一行完整记录了响应（原文节选）：

```json
{"result":{"blVersionCheckResults":[{
  "blVersionInfo":{"currentBlVersionNumber":"MAG-AN00 10.0.0.175(C00E170R8P1)",
                   "laneName":"HotaLane_MAG-AN00_all_cn_C00_R8",
                   "targetBlVersionNumber":"MAG-AN00 10.0.0.175(C00E170R8P1)",
                   "updateAction":"recovery"},
  "descriptPackageId":"877311",
  "targetBlComponents":[
    {"displayVersionNumber":"MAG-LGRP1-CHN 10.0.0.175","versionPackageType":2},
    {"displayVersionNumber":"MAG-AN00-CUST 10.0.0.170(C00)","versionPackageType":3},
    {"displayVersionNumber":"MAG-AN00-PRELOAD 10.0.0.1(C00R8)","versionPackageType":4}],
  "updatePackages":[
    {"packageIndex":1,"versionId":"877297","versionPackageType":2},
    {"packageIndex":2,"versionId":"857230","versionPackageType":3},
    {"packageIndex":3,"versionId":"712636","versionPackageType":4}],
  "versionList":[
    {"url":"http://update.hihonorcdn.com/TDS/data/bl/files/v877297/f1/","versionNumber":"MAG-LGRP1-CHN 10.0.0.175"},
    {"url":"http://update.hihonorcdn.com/TDS/data/bl/files/v857230/f1/","versionNumber":"MAG-AN00-CUST 10.0.0.170(C00)"},
    {"url":"http://update.hihonorcdn.com/TDS/data/bl/files/v712636/f1/","versionNumber":"MAG-AN00-PRELOAD 10.0.0.1(C00R8)"},
    {"url":"http://update.hihonorcdn.com/TDS/data/bl/files/v877311/f1/","versionId":"877311"}]
}]}}
```

### 2.3 ID 对照表

| 角色 | versionId | 说明 |
|---|---|---|
| base（主固件，含 boot） | **877297** | `MAG-LGRP1-CHN 10.0.0.175` |
| cust | 857230 | `MAG-AN00-CUST 10.0.0.170(C00)` |
| preload | 712636 | `MAG-AN00-PRELOAD 10.0.0.1(C00R8)` |
| 描述包 / changelog | 877311 | 手机端 `changelogRootPathList` 用的就是它 |

---

## 3. 从 versionId 定位真实包

包描述目录：

```
http://update.hihonorcdn.com/TDS/data/bl/files/v877297/f1/
```

**注意：目录本身返回 404 是正常的**，`update.zip`、`meta.json` 也都不存在。
真正有用的是 `/f1/full/filelist.xml`：

```xml
<packageType>full</packageType>
<packageSolution>base</packageSolution>
<VirtualAB>
  <payloadOffset>828</payloadOffset>
  <fileSize>8088115742</fileSize>
  <cowsize>11467857920</cowsize>
  <switchSlotOnReboot>1</switchSlotOnReboot>
</VirtualAB>
<files><file>
  <spath>update_full_base.zip</spath>
  <sha256>F612730B62B690A67399E3F63A584823BE1AC3DF46C5387F6985BF1AB0DE1C19</sha256>
  <size>8088123136</size>
</file></files>
```

得到全量包地址（8,088,123,136 B ≈ 8.09 GB）：

```
http://update.hihonorcdn.com/TDS/data/bl/files/v877297/f1/full/update_full_base.zip
```

### 包内结构（A/B payload，非逐镜像）

zip 起始处的 `META-INF/com/android/metadata` 已写明：

```
ota-property-files=payload_metadata.bin:828:341845,
                  payload.bin:828:8088115742,
                  payload_properties.txt:8088116622:156,
                  VERSION.mbn:...
```

即 zip 里**没有 boot.img**，只有 `payload.bin`（CrAU 格式）。所以必须解析 payload。

---

## 4. 只取 boot 分区：两级 Range

### 4.1 zip 尾部中央目录

`update_full_base.zip` 支持 Range（`206 Partial Content`），但 **`HEAD` 返回 403**，取长度只能用 `Range: bytes=0-0` 读 `Content-Range`。

### 4.2 payload 头部（CrAU）

在 zip 偏移 828 处：

```
43 72 41 55 | 00 00 00 00 00 00 00 02 | 00 00 00 00 00 05 36 32 | 00 00 01 0B
"CrAU"      | version = 2 (u64 BE)     | manifest_size = 341554  | meta_sig = 267
```

因此 payload 数据基址 = `24 + 341554 + 267 = 341845`
（与 `payload_metadata.bin` 的长度 341,845 完全吻合，可作交叉校验）。

### 4.3 manifest（protobuf）寻址

`DeltaArchiveManifest` 用极简 protobuf 走一遍即可，无需 `.proto`：

```
manifest.partitions[13]  → PartitionUpdate
    partition_name = 1
    operations     = 8   → InstallOperation
        type       = 1   (REPLACE=0 / REPLACE_BZ=1 / REPLACE_XZ=8 / ZERO=6)
        data_offset= 2   （相对 payload.bin 起点）
        data_length= 3
        dst_extents= 6   → (start_block=1, num_blocks=2)，块大小 4096
```

实测：`partitions = 58`，`boot` 分区 `operations = 48`。

任一数据块的绝对位置：

```
zip 偏移 = 828 + 341845 + data_offset
```

按 `dst_extents` 落位、按 `type` 解压（bz2 / lzma / 原样 / 补零），拼出整个 boot 分区。

---

## 5. 提取与校验

```bash
U="http://update.hihonorcdn.com/TDS/data/bl/files/v877297/f1/full/update_full_base.zip"

# 1) 远程读 zip 目录（确认成员）
python remote_zip.py list "$U"

# 2) 解析 payload 的 boot 分区
python payload_boot.py "$U" 828 boot.img boot

# 3) 解析 boot header + 校验内核串
python extract_boot.py --verify boot.img
```

输出：

```
payload version=2 manifest=341554 meta_sig=267
manifest ok (341554 bytes), data base in payload = 341845
partitions: 58
partition boot: 48 operations
wrote boot.img (100663296 bytes / 96.0 MB)

file      : boot.img (100663296 bytes)
header_ver: 4
kernel    : 52967936 bytes
ramdisk   : 0 bytes
header_sz : 1584
linux_banner: 5.15.180-android13-8-g938a6e3184bd (build-user@build-host) (Android (8508608, based on r450784e) clang version 14.0.7 ...
MATCH     : kernel string found at [32961289, 33486543, 33504303, 34298544, 36045702]
RESULT    : EXACT_MATCH
```

### 产物

| 文件 | 大小 | sha256 |
|---|---|---|
| `boot.img` | 100,663,296 B | `a69c91f1e3a0e22c8b13d84a9e7af6d8eba60771ef9a0180c7710dc9c6415be1` |
| `Image`（裸 ARM64） | 52,967,936 B | `571a566de0f81acab1f305d94f84671052b9dc666e96fcbb6bd4aba3bbd8870d` |

`Image` 关键字段：

```
kernel_offset : 0x1000 (4096)
arm64 magic   : 0x644d5241  → 合法 ARM64 Image
text_offset   : 0x0
image_size    : 54,853,632
banner        : Linux version 5.15.180-android13-8-g938a6e3184bd ...
```

`Image` 可直接反汇编（起点即代码），无需再解压。

---

## 6. 踩过的坑

1. **boot v4 内核按 4096 对齐**，不是紧跟 1584 字节头。按 `header_size` 取内核会在偏移 56 读到 `0x0`，
   误判为「不是 ARM64 Image」。正确起点 = `align(header_size, 4096) = 0x1000`。
2. **`bl/files/v<id>/f1/` 目录 404 是正常现象**，只有 `changelog.xml`（描述包）与 `full/filelist.xml` 存在。
   直接猜 `update.zip` 必失败。
3. **`HEAD` 被 CDN 拒绝（403）**，取文件长度要用 `Range: bytes=0-0` + `Content-Range`。
4. **`updateAction` 猜不出来**：`check` 接口对当前版本永远无包；必须经由套件 `onestopCheck` 的
   `recovery` 分支才会暴露 `versionId`。
5. 套件「系统修复」在本机会判定「设备系统正常，无需修复」而**不下载**——这不影响取 ID，
   因为日志在检查阶段就已写入完整响应。

---

## 7. 脚本清单（`mag-an00\`）

| 脚本 | 作用 |
|---|---|
| `remote_zip.py` | 远程 ZIP：EOCD/ZIP64 定位、中央目录解析、按成员 Range 取回 |
| `payload_boot.py` | CrAU 头 + protobuf manifest 解析，只取指定分区的数据块 |
| `extract_boot.py` | boot header v0–v4 解析、gz/lz4 解包、内核串比对（`--verify`） |
| `replay_check.py` / `replay_matrix.py` / `replay_modes.py` / `replay_fullpkg.py` | OTA `check` 接口回放与参数穷举（用于证明「查不到」） |
| `ota_hunt.py` / `ota_url_watch.py` / `proxylog.py` | 设备端 OTA 请求抓取与 URL 监听 |
| `conn_scan.py` / `win.py` / `watch_download.py` | 连接采样、窗口操作、下载监控等辅助 |

---

## 8. 复现要点速查

```text
versionId(base) : 877297
清单            : http://update.hihonorcdn.com/TDS/data/bl/files/v877297/f1/full/filelist.xml
全量包          : http://update.hihonorcdn.com/TDS/data/bl/files/v877297/f1/full/update_full_base.zip
zip 内 payload  : 偏移 828，CrAU v2
manifest        : 341,554 B；meta_sig 267 B；数据基址 341,845
boot 分区       : 48 ops → 100,663,296 B
内核            : boot.img 偏移 0x1000，52,967,936 B，magic 0x644d5241
内核串          : 5.15.180-android13-8-g938a6e3184bd  ← EXACT_MATCH
```

设备侧全程零改动：未解锁、未刷机、未安装任何应用，`http_proxy` 保持 `:0`。
