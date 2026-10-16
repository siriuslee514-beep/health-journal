# 手机和电脑使用同一账本

## 当前状态

本地 skill 和 SQLite 可以在当前电脑工作。当前未配置云端后端、定时任务或三星账号授权；不能承诺手机已能自动调用本地 skill，也不能声称能实时读取手表。

用户希望手机和电脑同步，后续需选择可访问的云端主账本和运行入口。桌面安装 skill 与手机 ChatGPT 加载规则是不同配置步骤，本地目录不会自动成为手机执行环境。

## 接入已有云端工具

用户选定并授权服务、且环境有相应连接器时，沿用 [数据语义](data-contract.md)。先检查工具是否支持读、写、修改和导出；连接器专用 skill 存在时使用其指导。只有搜索权限时不要承诺写入。

- 选择一份主账本，记录类型、稳定标识和版本。远端不可用时不静默写本地副本并声称同步成功。
- 仅本人可见，不为接入方便开启公开链接。上传既有日志需要用户对服务和数据范围的授权；封装/安装 skill 不授权上传。
- 至少保留 profile_versions、events、event_history、day_status 的语义。事件 id 稳定，重试去重，编辑带 revision，餐食变更取消完整日标记。
- 日期用用户当地日期，审计时间戳含时区；跨时区保留原始时间和来源。
- 写入后读回 id/版本；冲突先获取最新版本，不覆盖另一设备更改。
- JSON/CSV 导出是迁移材料，不代表自动双向同步。不要把正在使用的 SQLite 文件放进网盘并在多设备同时写入。

## 普通手机 ChatGPT

可在专用项目提供本 skill 的规则和个人目标作为上下文，但聊天历史/项目记忆不等于结构化账本。可靠持久读写可通过专用 GPT Actions 或授权连接工具访问同一云端服务，实际能力取决于账号、客户端和连接工具。

官方资料（核对日期 2026-10-16）：[Skills 定位](https://developers.openai.com/plugins/concepts/skills)、[项目与聊天](https://learn.chatgpt.com/docs/projects?surface=app)、[手机上的 Work](https://developers.openai.com/training/walkthroughs/working-on-your-phone)、[GPT Actions](https://developers.openai.com/api/docs/actions/introduction)。

仅要求封装 skill 时，交付本地可用包并说明云同步状态，不擅自创建网站、账号、云数据库、付费服务或自动化。
