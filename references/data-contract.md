# 本地账本命令和数据格式

以下示例是模拟数据，与真实用户档案无关。所有数字使用 kcal、g、kg、cm、分钟；未知值省略或用 null，不写假 0。JSON 使用 UTF-8。把内容写入一个临时 JSON 文件再通过 `--input` 传入，不把用户文本拼进 shell 命令。

## 命令

统一前缀：`python <skill目录>/scripts/journal.py --store <数据目录>`。Windows 目录示例为 `E:/HealthJournal/data`；实际主账本目录需由用户确定。

| 子命令 | 用法 |
|---|---|
| init | `init --input <profile.json>`，只初始化，不覆盖 |
| profile | `profile [--date YYYY-MM-DD]` 读取当天生效档案；`profile --input <完整档案.json>` 保存新版本 |
| record | `record --input <event.json>`，同 id 同内容重试去重，同 id 不同内容报冲突 |
| get | `get --id <事件id>`，读取 revision 和状态 |
| edit | `edit --id <id> --revision <当前版本> --input <完整事件.json>` |
| void | `void --id <id> --revision <当前版本>`，撤销且保留历史 |
| complete | `complete --date YYYY-MM-DD`，仅用户确认全天已记全后使用；`--incomplete` 取消 |
| day | `day --date YYYY-MM-DD` |
| week | `week --end YYYY-MM-DD --days 7`，支持 1–7 天；包含独立的最近两个 7 日体重窗口 |
| calculate-plan | `calculate-plan --age 30 --sex male --height 175 --weight 70 --energy 2400 [--protein-per-kg 2 --fat-share 0.25]`，独立计算，不写档案 |
| estimate-exercise | `estimate-exercise --weight 70 --minutes 30 --met 5`，MET 必须来自适当来源，独立计算不自动记入 |
| export | `export --format json或csv --out <新路径>`，含档案版本、事件、修订历史及完整日状态 |
| backup | `backup --out <新路径.sqlite>`，SQLite 在线一致性备份 |

成功输出 `{"ok":true,"result":...}`，错误输出 `{"ok":false,"error":...}` 并返回非零退出码。导出和备份不会覆盖已有文件。删除账本/批量清空不在脚本能力内。

## 个人档案

```json
{
  "effective_from": "2026-10-16",
  "timezone": "Asia/Singapore",
  "storage_mode": "local",
  "age_years": 30,
  "sex_for_equation": "male",
  "height_cm": 175,
  "reference_weight_kg": 70,
  "goal": "fat_loss_preserve_muscle",
  "training": {"days_per_week": 3, "notes": "模拟训练安排"},
  "medical_context": "以用户实际提供为准，未知不填无疾病",
  "targets": {
    "energy_kcal": 2400,
    "protein_g": 140,
    "fat_g": 65,
    "carb_g": 313.75,
    "fiber_g": 25,
    "fruit_veg_g": 400
  }
}
```

档案更新应写完整对象并明确 `effective_from`。历史日按当时生效版本计算，不用新目标重算旧报告。更正历史版本需要用户明确要求，并保留原始版本。

## 事件通用结构

顶层只能有 `id`、`date`、`kind`、`data`。id 使用 UUID 或稳定的 ASCII 事件编号（最长 96 字符）。每个 data 都需要 `description`。输出附加 revision、status、created_at、updated_at；编辑输入不包含这些输出字段。

### 餐食 meal

```json
{
  "id": "sample-lunch-001",
  "date": "2026-10-16",
  "kind": "meal",
  "data": {
    "description": "午餐吃了一份鸡饭，米饭约一碗，鸡肉带皮。",
    "meal": "lunch",
    "portion_note": "外食；熟米饭一碗，油和鸡肉重量未知",
    "basis": "portion_estimate",
    "source": "模拟的份量估算，用于演示；正式记录需实际依据",
    "uncertainty_note": "油和份量使估算存在较大误差",
    "nutrition": {"energy_kcal": 650, "protein_g": 30, "fat_g": 25, "carb_g": 76}
  }
}
```

nutrition 仅支持 energy_kcal、protein_g、fat_g、carb_g、fiber_g、fruit_veg_g。basis 为 label、database、recipe、portion_estimate、unknown。有营养数值需要 source，可记录标签来源、数据库链接或明确的估算说明；不伪造出处。未知纤维、蔬果不能因未写而变成 0。

### 单次训练 exercise

```json
{
  "id": "sample-workout-001",
  "date": "2026-10-16",
  "kind": "exercise",
  "data": {
    "description": "力量训练加有氧，设备显示消耗 400 kcal，原始口径未确认。",
    "activity": "strength_and_cardio",
    "duration_min": 80,
    "energy_kcal": 400,
    "energy_scope": "unknown",
    "source": "Samsung watch，用户转述",
    "device_label": "保留手表原始字段名称",
    "training_notes": "主要动作、组次、重量或主观训练强度可放这里"
  }
}
```

energy_scope：active 指明确标为活动/动态热量；session_total 为包含该时段静息消耗的训练总消耗；unknown 为不清楚。不能根据设备品牌臆测口径。每种口径单独汇总，不把它们加成一个净消耗。

### 日活动汇总 activity

```json
{
  "id": "sample-activity-001",
  "date": "2026-10-16",
  "kind": "activity",
  "data": {
    "description": "日终三星健康汇总，已确认是全天总消耗。",
    "steps": 8500,
    "active_energy_kcal": 600,
    "total_energy_kcal": 2500,
    "day_complete": true,
    "source": "Samsung Health 日终截图"
  }
}
```

同日有多条 activity 时取最后更新的一条快照，不相加。`day_complete:true` 必须来自整日汇总确认；下午截图不能当全天值。仅当饮食已记全、所有餐食能量已知、日终总消耗已知时，才输出 `estimated_daily_deficit_kcal = total_energy_kcal − intake`，仍标为设备估算差值。默认未确认时为 null。

### 测量 body

```json
{
  "id": "sample-body-001",
  "date": "2026-10-16",
  "kind": "body",
  "data": {
    "description": "晨起如厕后、早餐前测量",
    "weight_kg": 70,
    "waist_cm": 80,
    "condition": "morning",
    "source": "体重秤和软尺"
  }
}
```

condition 为 morning、other 或 unknown。body_fat_pct 可选，需注明设备估计。每个日期只选最后更新的一条 morning 体重参与均值，不混入晚间称重。

### 身体感受 wellbeing

```json
{
  "id": "sample-feeling-001",
  "date": "2026-10-16",
  "kind": "wellbeing",
  "data": {
    "description": "昨晚睡了7小时，今天精神一般，无明显不适。",
    "sleep_hours": 7,
    "energy_score": 3,
    "hunger_score": 2,
    "fatigue_score": 3,
    "symptoms": []
  }
}
```

评分 1–5 仅用户愿意时填写。energy 越高精神越好；hunger 和 fatigue 越高表示越明显。自由文字感受可以直接记录，不强迫量表。

## 日报与周报口径

`known_intake` 是已知数值之和，缺失不填 0；`missing_nutrients` 给缺失条数。`remaining_vs_daily_target` 是目标减已知摄入，不是要求补吃。未记录日的摄入为 null；只有用户明确标为“全天已记全”且无餐食事件时，才把该日视为明确的零摄入。

周均营养仅使用“全天记全且该营养素无缺失”的日期，逐项返回 `nutrient_coverage_days`，不能将一天少量记录当作完整日，也不能把不同覆盖率的均值当成整周精确摄入。周报保留 daily，可据实际记录解释睡眠、腰围和训练表现。
