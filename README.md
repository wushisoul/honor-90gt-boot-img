# 荣耀 90 GT（MAG-AN00）原厂 boot.img 获取与提取

从荣耀官方 OTA 全量包中取出 `boot.img`，并校验内核版本串。

- **目标设备**：荣耀 90 GT / `MAG-AN00` / SM8550 / Android 16 + MagicOS 10
- **系统版本**：`MAG-AN00 10.0.0.175(C00E170R8P1)`
- **内核**：`5.15.180-android13-8-g938a6e3184bd`（构建 2026-08-07 09:10:03 UTC）
- **结果**：`EXACT_MATCH`

## 产物

| 文件 | 大小 | sha256 |
|---|---|---|
| `bin/boot.img` | 100,663,296 B | `a69c91f1e3a0e22c8b13d84a9e7af6d8eba60771ef9a0180c7710dc9c6415be1` |
| `bin/Image`（裸 ARM64） | 52,967,936 B | `571a566de0f81acab1f305d94f84671052b9dc666e96fcbb6bd4aba3bbd8870d` |

两个文件均已随仓库分发。GitHub 对单文件 50 MB 以上会提示改用 LFS（硬上限 100 MB），
`bin/boot.img` 96 MB、`bin/Image` 50.5 MB 都在上限内，直接 clone 即可，无需 LFS。

## 为什么绕这么远

设备 `ro.boot.flash.locked=1`（BL 永久锁）、无 root：

| 手段 | 结果 |
|---|---|
| `dd /dev/block/sde33`（boot_a） | 分区 `0600 root:root`，读出 0 字节 |
| `fastboot fetch boot_a` | 锁 BL，必被拒 |
| OUC ContentProvider | `requires HW_SIGNATURE_OR_SYSTEM` |
| OTA `check` 接口 | 对“已是最新”的设备恒返回 `101003404 ota packageInfo is not exist` |

唯一可行来源是**官方 OTA 全量包**，入口藏在 PC 套件「系统修复」的接口里。

## 关键参数

```
# 组件 versionId（来自 HonorSuite 的 recovery 响应）
base    877297   MAG-LGRP1-CHN 10.0.0.175
cust    857230   MAG-AN00-CUST 10.0.0.170(C00)
preload 712636   MAG-AN00-PRELOAD 10.0.0.1(C00R8)
descript 877311  changelog 用

# 清单
http://update.hihonorcdn.com/TDS/data/bl/files/v877297/f1/full/filelist.xml

# 全量包（8,088,123,136 B）
http://update.hihonorcdn.com/TDS/data/bl/files/v877297/f1/full/update_full_base.zip

# 包结构
zip 内 payload.bin 起始偏移 828，CrAU v2
manifest 341,554 B，meta_sig 267 B → payload 数据基址 341,845
boot 分区 48 个 operation → 100,663,296 B
内核在 boot.img 偏移 0x1000，52,967,936 B，magic 0x644d5241
```

## 复现

```bash
U="http://update.hihonorcdn.com/TDS/data/bl/files/v877297/f1/full/update_full_base.zip"

python tools/remote_zip.py list "$U"                 # 远程读 zip 目录
python tools/payload_boot.py "$U" 828 boot.img boot  # 只取 boot 分区
python tools/extract_boot.py --verify boot.img        # 校验内核串
```

预期输出：

```
partitions: 58
partition boot: 48 operations
wrote boot.img (100663296 bytes / 96.0 MB)

header_ver: 4
linux_banner: 5.15.180-android13-8-g938a6e3184bd ...
RESULT    : EXACT_MATCH
```

## 目录

```
docs/MAG-AN00_boot.img_获取记录.md   完整过程记录（含接口、ID、字段、踩坑）
data/filelist_v877297.xml            官方清单原文
data/changelog_v877311.xml           官方更新说明原文
tools/remote_zip.py                  远程 ZIP：EOCD/ZIP64 + 中央目录 + 按成员 Range
tools/payload_boot.py                CrAU + protobuf manifest，按分区取数据块
tools/extract_boot.py                boot header v0–v4 解析 + 内核串校验
tools/replay_*.py                    OTA check 接口回放与参数穷举（用于证明「查不到」）
tools/ota_*.py                       设备端请求抓取与 URL 监听
```

## 说明

仅用于本人设备的固件分析与逆向研究。`bin/` 下的 `boot.img` / `Image` 为厂商版权文件，
版权归荣耀所有，此处仅作个人研究与备份用途，请勿商用或再分发；
脚本只做公开 OTA 服务器上的 HTTP Range 读取与格式解析。
