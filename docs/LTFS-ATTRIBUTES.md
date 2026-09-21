# LTFS 属性查询

在原有两个身份属性之上，提供 **59 个可查询属性**。查询来自当前挂载的
LTFS 标签、索引、MAM 内存状态或该挂载持有的驱动器句柄；不读取历史 schema、
不另开物理磁带设备、不写磁带。GUI 和挂载参数没有增加。

## 调用示例

以下命令从 LTOG 项目根目录运行；安装包中在 `tools` 目录运行同名脚本。
需要 Python 3，脚本和 `ltfs_attributes.json` 必须放在一起。

```powershell
# 离线列出支持的名称、类别、作用范围、单位和 Windows EA 可见性
python tools/ltfs_identity.py --list

# 保持原有身份查询方式和 JSON 输出不变
python tools/ltfs_identity.py T:\

# 按名称查询，属性名不区分大小写；--get 可重复
python tools/ltfs_identity.py T:\ --get ltfs.volumeName --get ltfs.indexGeneration

# 分组查询，可重复组合
python tools/ltfs_identity.py T:\ --group volume --group index
python tools/ltfs_identity.py T:\ --group capacity
python tools/ltfs_identity.py T:\ --group health --group alerts --group encryption

# 包含全部类别；不适用或不支持的属性单独标记
python tools/ltfs_identity.py T:\ --all

# 指定挂载内的相对路径，查询文件/目录元数据（不读取文件正文）
python tools/ltfs_identity.py T:\ --path '备份/文件.zip' --group file
```

`--list` 是支持清单，不代表当前磁带的所有属性都有值。省略 `--group` 的
`--path` 查询默认使用 `file` 类别。文件路径不能是绝对路径、设备路径、ADS
或包含 `..`；根目录属性与文件路径组合会报 `invalid_scope`。

## 结果与错误

默认身份命令仍返回 `ltfs.volumeSerial`、`ltfs.volumeUUID`。
扩展命令返回以下结构，数值仍保留 LTFS 原始文本，避免大整数精度损失：

```json
{
  "status": "ok",
  "mountPoint": "T:\\",
  "path": "T:\\",
  "volumeUUID": "11111111-2222-4333-8444-555555555555",
  "attributes": {
    "ltfs.indexGeneration": {"status": "ok", "value": "42"}
  }
}
```

| 单项 status | 含义 |
| --- | --- |
| `ok` | 获取到原始 UTF-8 文本；有确定单位时包含 `unit` |
| `empty` | Getter 返回空值，不能解释为数值零 |
| `unavailable` | 当前对象无此属性，如空文件无起始块、无策略时无最大文件大小 |
| `unsupported` | LTFS 返回不支持，或健康计数为 `-1` |
| `unknown` | 加密状态返回 unknown，不能解释为未加密 |
| `too_large` | 属性超过 4032 字节，未返回截断值 |
| `read_error` | 单项查询失败，保留原始 `ltfsError` |
| `invalid_encoding` | 属性值不是合法 UTF-8 |

全部单项为 `ok` 时退出码 0；存在其它单项状态时顶层为 `partial`、退出码 **8**。
例如虚拟磁带不支持健康计数，`--all` 返回 8 是正常的能力报告。空字符串也会使
报告为 partial。权限失败返回 4，旧引擎不支持扩展查询返回 6，协议或 I/O 错误
返回 7。未挂载/路径缺失返回 3；名称、路径和范围错误返回 2。

传输失败、介质就绪检查失败或查询期间 UUID 变化，会丢弃整份报告；失败 JSON
不携带先前已经读到的属性。每次查询使用新文件系统句柄，没有持久缓存。
每条响应携带挂载 UUID；一组查询要求 UUID 一致。文件查询先确定指定根目录的
UUID，防止跨挂载的路径重定向产生错误归属。

这些值是查询时观察到的结果，不是整卷事务快照：同一 UUID 的挂载若正在写入，
索引代数、容量等可能在各单项之间改变；调用方不能把一份报告当成写入事务锁。

## 接口实现与兼容性

Windows EA 枚举可读取身份在内共 29 个廉价根目录元数据属性。健康、容量、加密、
告警及文件属性不会加入 EA 自动枚举：WinFsp 的按名称 EA 查询内部仍会读取
整个 EA 列表，把诊断属性加入列表将导致普通身份查询也访问硬件。

完整清单采用 WinFsp 2.1 已支持的 `DeviceIoControl → FUSE ioctl` 转发，无需替换
WinFsp 驱动或 DLL。打开明确的挂载根目录/文件，要求 `FILE_READ_EA`，共享
read/write/delete，`OPEN_EXISTING`，`FILE_FLAG_BACKUP_SEMANTICS`；示例同时设置
`FILE_FLAG_OPEN_REPARSE_POINT`，不跟随最终符号链接。只打开文件系统对象。

第三方应用可直接调用以下二进制协议，不必调用 Python：

- 属性名称、类别及固定命令 ID 在 `tools/ltfs_attributes.json`。
- 控制码：`(0xC657 << 16) | (id << 2)`，对应 WinFsp 自定义设备类型。
- **输入长度必须为 0**，输出长度必须为 **4096**；采用输出专用命令。
- Windows 的转发给 FUSE 的命令为 `0x90000000 | id`。
- 未知 ID、输入方向、错误长度或 FUSE flags 会在访问介质之前被拒绝。
- 仅接受清单内的 getter；接口没有 setter、删除、同步、转储或任意命令功能。
- 失败的 `DeviceIoControl` 输出不可使用；成功返回固定 4096 字节：

| 字节偏移 | 类型 | 内容 |
| --- | --- | --- |
| 0 | uint32 LE | magic `0x474F544C`，即 `LTOG` |
| 4 | uint32 LE | 协议版本 1 |
| 8 | int32 LE | 0 或负数 LTFS 错误码 |
| 12 | uint32 LE | value 字节数，最大 4032；错误时 0 |
| 16 | char[40] | 当前挂载 UUID，NUL 补齐 |
| 56 | byte[8] | 保留，0 |
| 64 | byte[4032] | UTF-8 原始值，按 length 读取，不依赖终止符 |

接口不会把单项的“空、不支持、读取失败”伪装成零，也不会为旧引擎回退到缓存。
旧引擎原来的 EA 接口保持可用，但不认识新的控制码。

## 属性清单

下表名称省略共同前缀 `ltfs.`。`--list` 提供机器可读的完整信息。

| 类别 | 属性 |
| --- | --- |
| identity | volumeSerial, volumeUUID |
| volume | volumeName, volumeFormatTime, volumeBlocksize, volumeCompression, labelVersion, labelCreator, partitionMap |
| index | indexGeneration, indexTime, indexVersion, indexLocation, indexPrevious, indexCreator, commitMessage |
| policy | policyExists, policyAllowUpdate, policyMaxFileSize |
| software | softwareVersion, softwareFormatSpec, softwareVendor, softwareProduct |
| mam | mamBarcode, mamVolumeName, mamApplicationVendor, mamApplicationName, mamApplicationVersion, mamApplicationFormatVersion |
| capacity | mediaDataPartitionTotalCapacity, mediaDataPartitionAvailableSpace, mediaIndexPartitionTotalCapacity, mediaIndexPartitionAvailableSpace |
| health | mediaLoads, mediaRecoveredWriteErrors, mediaPermanentWriteErrors, mediaRecoveredReadErrors, mediaPermanentReadErrors, mediaPreviousPermanentWriteErrors, mediaPreviousPermanentReadErrors, mediaBeginningMediumPasses, mediaMiddleMediumPasses, mediaEfficiency, mediaDatasetsWritten, mediaDatasetsRead, mediaMBWritten, mediaMBRead |
| alerts | mediaStorageAlert |
| encryption | mediaEncrypted, driveEncryptionState, driveEncryptionMethod |
| file | fileUID, createTime, modifyTime, accessTime, changeTime, backupTime, partition, startblock |

容量单位为本引擎转换后的 MiB（不是字节）；块大小和策略大小是字节。
健康统计中的 MB 单位沿用后端含义，不擅自换算。位置为分区字母和块号，
不是文件偏移量。`mamBarcode` 与 LTFS 标签中的 `volumeSerial` 不混用。
MAM 类别返回该挂载读取到的内存状态，并非每次强制重新读取所有 MAM。

未加入操作型属性 `ltfs.sync`、`ltfs.driveCaptureDump`，也不开放任意厂商私有
属性。`ltfs.volumeLockState` 的旧 getter 会更新锁状态且存在错误路径锁处理
问题，本次不通过新接口开放。修改卷名、策略和时间等现有上游 setter 不在
本次接口范围内。CLI 的 `--all` 仅指上述明确的只读清单。

## 验证与部署

运行 `python -m unittest discover -s tests -v`、`bash tests/native_identity.sh`
及 `python tests/emulator_identity.py`。集成测试在普通权限下创建本地磁盘虚拟
介质，准备空文件后只读挂载，逐项查询 59 个属性，并验证文件查询、同盘符换
介质、断开失效和介质文件哈希不变。真实磁带硬件计数是否支持仍需下次使用
新引擎挂载后验证。

当前物理 `T:` 挂载不被测试替换或卸载。部署新引擎需在磁带工作结束后正常
卸载并重新挂载；本次不操作该挂载，也不修改 TapeBackup。
