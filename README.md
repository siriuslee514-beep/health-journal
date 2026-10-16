# Health Journal · 饮食运动健康日记

一个通过聊天记录饮食、运动、身体测量和日常感受的 Codex skill。使用本地 SQLite 保存可修改的账本，并用 Python 确定性计算营养累计、目标差额与周报。

## 功能

- 自然语言记餐，保留份量、来源、估算依据和缺失项。
- 记录训练类型、时长和设备消耗，区分活动热量、训练总消耗及全天总消耗。
- 计算个人营养目标，记录带生效日期的目标版本。
- 记录体重、腰围、设备体脂估计、睡眠、饥饿与疲劳感。
- 生成每日小结、饮食完整度统计、周均摄入及晨重趋势。
- 支持重试去重、带版本更正、撤销留痕、JSON/CSV 导出和 SQLite 备份。

## 安装与使用

需要支持 skills 的 Codex 环境，以及 Python 3.10 或更高版本。运行脚本仅依赖 Python 标准库。

将仓库克隆到个人 skills 目录下的 `health-journal` 文件夹。例如 Windows PowerShell：

```powershell
git clone https://github.com/siriuslee514-beep/health-journal.git "$env:USERPROFILE\.codex\skills\health-journal"
```

如果该目录已经存在，先检查已有安装，不要直接覆盖。

调用示例：

```text
$health-journal 午餐吃了一碗米饭、一份鸡肉和蔬菜，份量没有称重。
```

```text
$health-journal 记录今天的力量训练和有氧，设备显示400 kcal，暂时不清楚是不是活动热量。
```

```text
$health-journal 总结最近一周的饮食、训练、体重和恢复情况。
```

第一次使用时提供个人资料、目标和主账本位置。不要把别人的营养方案直接用于自己。数据格式和脚本命令见 [data-contract.md](references/data-contract.md)。

## 保存与同步

实际健康数据保存在 skill 文件夹之外。Windows 默认路径示例是 `E:/HealthJournal/data`；也可以使用 `--store` 或 `HEALTH_JOURNAL_HOME` 指定其他位置。

当前实现为本地账本。手机与电脑共用云端账本需要另行配置运行入口、后端和授权；仓库不包含云服务凭据，也不会自动连接三星账号或读取手表。详见 [sync.md](references/sync.md)。

仓库不包含作者的个人档案、餐食、身体测量或真实日志。[data-contract.md](references/data-contract.md) 中的数据仅用于演示。

## 营养规则

计算顺序为：确定个人能量目标，按选定系数计算蛋白质和脂肪，再分配碳水，并结合训练供能、饮食质量和持续记录复核。

营养参数属于可调整的初始方案。记录和设备数值可能有估算误差；漏记不会被当成零摄入，单次运动消耗也不会被当成全天消耗。来源和适用边界见 [nutrition-rules.md](references/nutrition-rules.md)。

## 文件结构

```text
SKILL.md
agents/openai.yaml
scripts/journal.py
references/data-contract.md
references/nutrition-rules.md
references/sync.md
```
