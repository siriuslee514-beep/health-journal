#!/usr/bin/env python3
"""Private, local health journal. Standard-library-only, Python 3.10+."""

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys

SG = timezone(timedelta(hours=8), "Asia/Singapore")
NUTRIENTS = ("energy_kcal", "protein_g", "fat_g", "carb_g", "fiber_g", "fruit_veg_g")
KINDS = ("meal", "exercise", "activity", "body", "wellbeing")


class JournalError(ValueError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def today():
    return datetime.now(SG).date().isoformat()


def day_value(value):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except ValueError:
        raise JournalError("日期必须是 YYYY-MM-DD。") from None
    return value


def number(value, field, minimum=0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise JournalError(f"{field} 必须是有限数值。")
    if value < minimum or (maximum is not None and value > maximum):
        raise JournalError(f"{field} 超出允许范围。")
    return value


def clean_json(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError):
        raise JournalError("输入必须是有效 JSON，不允许 NaN 或 Infinity。") from None


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    clean_json(value)
    return value


def validate_profile(p):
    if not isinstance(p, dict):
        raise JournalError("个人资料必须是 JSON 对象。")
    day_value(p.get("effective_from"))
    number(p.get("age_years"), "age_years", 18, 120)
    number(p.get("height_cm"), "height_cm", 100, 250)
    number(p.get("reference_weight_kg"), "reference_weight_kg", 20, 400)
    if p.get("sex_for_equation") not in ("male", "female"):
        raise JournalError("sex_for_equation 应为 male 或 female；不适用时不要用本公式。")
    if p.get("timezone") != "Asia/Singapore":
        raise JournalError("此版本默认日期支持 Asia/Singapore；其他时区请显式指定所有日期并更新实现。")
    if p.get("storage_mode", "local") != "local":
        raise JournalError("本脚本仅操作本地账本，不能冒充已连接的云端后端。")
    t = p.get("targets")
    if not isinstance(t, dict):
        raise JournalError("缺少 targets。")
    for k in NUTRIENTS:
        number(t.get(k), f"targets.{k}")
    if t["energy_kcal"] <= 0:
        raise JournalError("热量目标必须大于零。")
    macro_energy = 4 * (t["protein_g"] + t["carb_g"]) + 9 * t["fat_g"]
    if abs(macro_energy - t["energy_kcal"]) > max(20, t["energy_kcal"] * 0.02):
        raise JournalError("目标热量与蛋白/脂肪/碳水的 4/9/4 折算不一致，请先复核。")
    clean_json(p)
    return p


def validate_event(e):
    if not isinstance(e, dict) or set(e) != {"id", "date", "kind", "data"}:
        raise JournalError("事件顶层需要且仅包含 id、date、kind、data。")
    if not isinstance(e["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}", e["id"]):
        raise JournalError("id 需要 1–96 个字母、数字或 _ . : -。")
    day_value(e["date"])
    if e["kind"] not in KINDS or not isinstance(e["data"], dict):
        raise JournalError("未知事件类型或 data 不是对象。")
    d = e["data"]
    if not isinstance(d.get("description"), str) or not d["description"].strip():
        raise JournalError("data.description 应保留原始描述。")
    if e["kind"] == "meal":
        if d.get("basis") not in ("label", "database", "recipe", "portion_estimate", "unknown"):
            raise JournalError("餐食需要 basis 说明营养数据依据。")
        n = d.get("nutrition", {})
        if not isinstance(n, dict) or set(n) - set(NUTRIENTS):
            raise JournalError("nutrition 含有不支持的字段。")
        for k, v in n.items():
            if v is not None:
                number(v, k)
        if any(v is not None for v in n.values()) and not d.get("source"):
            raise JournalError("有营养数值时需要 source（标签、来源链接或明确的估算说明）。")
    elif e["kind"] == "exercise":
        number(d.get("duration_min"), "duration_min", 0.01, 1440)
        if d.get("energy_scope") not in ("active", "session_total", "unknown"):
            raise JournalError("exercise 需要 energy_scope，未知口径用 unknown。")
        if d.get("energy_kcal") is not None:
            number(d["energy_kcal"], "energy_kcal")
        if not d.get("source"):
            raise JournalError("exercise 需要 source。")
    elif e["kind"] == "activity":
        if not d.get("source"):
            raise JournalError("activity 需要 source。")
        for k in ("steps", "active_energy_kcal", "total_energy_kcal"):
            if d.get(k) is not None:
                number(d[k], k)
        if d.get("total_energy_kcal") is not None and d.get("active_energy_kcal") is not None:
            if d["active_energy_kcal"] > d["total_energy_kcal"]:
                raise JournalError("活动热量不能大于同口径的全天总消耗。")
        if "day_complete" in d and not isinstance(d["day_complete"], bool):
            raise JournalError("activity.day_complete 必须是布尔值。")
    elif e["kind"] == "body":
        if not d.get("source"):
            raise JournalError("body 需要 source。")
        for k in ("weight_kg", "waist_cm"):
            if d.get(k) is not None:
                number(d[k], k, 0.01)
        if d.get("body_fat_pct") is not None:
            number(d["body_fat_pct"], "body_fat_pct", 0, 100)
        if d.get("condition") not in ("morning", "other", "unknown"):
            raise JournalError("body.condition 必须为 morning、other 或 unknown。")
    else:
        if d.get("sleep_hours") is not None:
            number(d["sleep_hours"], "sleep_hours", 0, 24)
        for k in ("energy_score", "hunger_score", "fatigue_score"):
            if d.get(k) is not None:
                number(d[k], k, 1, 5)
    clean_json(e)
    return e


class Journal:
    def __init__(self, store, create=False):
        self.store = Path(store).expanduser().resolve()
        self.path = self.store / "journal.sqlite3"
        if not create and not self.path.is_file():
            raise JournalError("账本不存在：请确认主账本位置，或先执行 init。")
        if create:
            self.store.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=15)
        self.db.row_factory = sqlite3.Row
        if self.db.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
            self.db.close()
            raise JournalError("账本版本不受当前脚本支持，请勿降级覆盖。")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS profile_versions (
            revision INTEGER PRIMARY KEY AUTOINCREMENT, effective_from TEXT NOT NULL,
            created_at TEXT NOT NULL, data_json TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, day TEXT NOT NULL, kind TEXT NOT NULL,
            revision INTEGER NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, data_json TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS events_day ON events(day, status);
          CREATE TABLE IF NOT EXISTS event_history (
            event_id TEXT NOT NULL, revision INTEGER NOT NULL, action TEXT NOT NULL,
            changed_at TEXT NOT NULL, snapshot_json TEXT NOT NULL,
            PRIMARY KEY(event_id, revision));
          CREATE TABLE IF NOT EXISTS day_status (
            day TEXT PRIMARY KEY, meals_complete INTEGER NOT NULL, updated_at TEXT NOT NULL);
          PRAGMA user_version=1;
        """)

    def close(self):
        self.db.close()

    def profile(self, day=None):
        sql = "SELECT * FROM profile_versions"
        args = ()
        if day is not None:
            sql += " WHERE effective_from <= ?"
            args = (day_value(day),)
        row = self.db.execute(sql + " ORDER BY effective_from DESC, revision DESC LIMIT 1", args).fetchone()
        return None if row is None else {"revision": row["revision"], "profile": json.loads(row["data_json"])}

    def set_profile(self, p, initial=False):
        validate_profile(p)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if initial and self.profile() is not None:
                raise JournalError("账本已经初始化，init 不会覆盖现有资料。")
            self.db.execute("INSERT INTO profile_versions(effective_from,created_at,data_json) VALUES(?,?,?)",
                            (p["effective_from"], stamp(), clean_json(p)))
        return self.profile(p["effective_from"])

    def get(self, event_id):
        row = self.db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise JournalError("没有找到该记录。")
        return {"id": row["id"], "date": row["day"], "kind": row["kind"],
                "revision": row["revision"], "status": row["status"],
                "created_at": row["created_at"], "updated_at": row["updated_at"],
                "data": json.loads(row["data_json"])}

    def _invalidate(self, day):
        self.db.execute("INSERT INTO day_status VALUES(?,0,?) ON CONFLICT(day) "
                        "DO UPDATE SET meals_complete=0,updated_at=excluded.updated_at", (day, stamp()))

    def record(self, event, revision=None):
        e = validate_event(event)
        data_json = clean_json(e["data"])
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.db.execute("SELECT * FROM events WHERE id=?", (e["id"],)).fetchone()
            if revision is None and old:
                if old["status"] == "active" and (old["day"], old["kind"], old["data_json"]) == (e["date"], e["kind"], data_json):
                    return {"saved": True, "duplicate": True, "record": self.get(e["id"])}
                raise JournalError("id 已存在但内容不同。更正请使用 edit 和当前 revision。")
            if revision is not None:
                if old is None or old["revision"] != revision or old["status"] != "active":
                    raise JournalError("版本冲突或记录已撤销；请先读取最新记录。")
            rev = 1 if old is None else old["revision"] + 1
            now = stamp()
            self.db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                            "day=excluded.day,kind=excluded.kind,revision=excluded.revision,status=excluded.status,"
                            "updated_at=excluded.updated_at,data_json=excluded.data_json",
                            (e["id"], e["date"], e["kind"], rev, "active", now, now, data_json))
            self.db.execute("INSERT INTO event_history VALUES(?,?,?,?,?)",
                            (e["id"], rev, "record" if old is None else "edit", now, clean_json(self.get(e["id"]))))
            if old and old["kind"] == "meal":
                self._invalidate(old["day"])
            if e["kind"] == "meal":
                self._invalidate(e["date"])
        return {"saved": True, "duplicate": False, "record": self.get(e["id"])}

    def void(self, event_id, revision):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.get(event_id)
            if old["revision"] != revision or old["status"] != "active":
                raise JournalError("版本冲突或记录已经撤销。")
            now = stamp()
            self.db.execute("UPDATE events SET status='void',revision=revision+1,updated_at=? WHERE id=?", (now, event_id))
            self.db.execute("INSERT INTO event_history VALUES(?,?,?,?,?)",
                            (event_id, revision + 1, "void", now, clean_json(self.get(event_id))))
            if old["kind"] == "meal":
                self._invalidate(old["date"])
        return {"saved": True, "record": self.get(event_id)}

    def complete(self, day, value=True):
        day_value(day)
        with self.db:
            self.db.execute("INSERT INTO day_status VALUES(?,?,?) ON CONFLICT(day) DO UPDATE SET "
                            "meals_complete=excluded.meals_complete,updated_at=excluded.updated_at", (day, int(value), stamp()))
        return {"saved": True, "date": day, "meals_complete": value}

    def events(self, day):
        return [self.get(r["id"]) for r in self.db.execute(
            "SELECT id FROM events WHERE day=? AND status='active' ORDER BY updated_at,id", (day,))]

    def day(self, day):
        day_value(day)
        events = self.events(day)
        status = self.db.execute("SELECT meals_complete FROM day_status WHERE day=?", (day,)).fetchone()
        complete = bool(status and status[0])
        meals = [e for e in events if e["kind"] == "meal"]
        total, missing = {}, {}
        for k in NUTRIENTS:
            values = [e["data"].get("nutrition", {}).get(k) for e in meals]
            known = [v for v in values if v is not None]
            total[k] = round(sum(known), 2) if known or (complete and not meals) else None
            missing[k] = len(values) - len(known)
        profile = self.profile(day)
        target = profile["profile"]["targets"] if profile else None
        remaining = {k: round(target[k] - total[k], 2) if total[k] is not None else None for k in NUTRIENTS} if target else None
        exercise = [e["data"] for e in events if e["kind"] == "exercise"]
        energy_by_scope = {}
        for scope in ("active", "session_total", "unknown"):
            items = [x for x in exercise if x["energy_scope"] == scope]
            vals = [x["energy_kcal"] for x in items if x.get("energy_kcal") is not None]
            energy_by_scope[scope] = {"known_kcal": round(sum(vals), 2) if vals else None,
                                      "missing_sessions": len(items) - len(vals)}
        activity = [e["data"] for e in events if e["kind"] == "activity"]
        latest_activity = activity[-1] if activity else None
        morning = [e["data"]["weight_kg"] for e in events if e["kind"] == "body"
                   and e["data"].get("condition") == "morning" and e["data"].get("weight_kg") is not None]
        full_energy = complete and missing["energy_kcal"] == 0 and total["energy_kcal"] is not None
        deficit = None
        if full_energy and latest_activity and latest_activity.get("day_complete") is True:
            if latest_activity.get("total_energy_kcal") is not None:
                deficit = round(latest_activity["total_energy_kcal"] - total["energy_kcal"], 2)
        return {"date": day, "recorded": bool(events or complete), "meals_complete": complete,
                "meal_count": len(meals), "known_intake": total, "missing_nutrients": missing,
                "estimated_meals": sum(e["data"]["basis"] in ("portion_estimate", "recipe", "unknown") for e in meals),
                "target_profile_revision": profile["revision"] if profile else None, "targets": target,
                "remaining_vs_daily_target": remaining, "exercise_sessions": len(exercise),
                "exercise_minutes": round(sum(x["duration_min"] for x in exercise), 2),
                "exercise_energy_by_scope": energy_by_scope, "daily_activity_snapshot": latest_activity,
                "estimated_daily_deficit_kcal": deficit, "morning_weight_kg": morning[-1] if morning else None,
                "events": events}

    def week(self, end, days=7):
        end_date = date.fromisoformat(day_value(end))
        if not 1 <= days <= 7:
            raise JournalError("周报 days 必须在 1–7。")
        daily = [self.day((end_date - timedelta(days=i)).isoformat()) for i in reversed(range(days))]
        means, coverage = {}, {}
        for k in NUTRIENTS:
            vals = [d["known_intake"][k] for d in daily if d["meals_complete"] and d["missing_nutrients"][k] == 0
                    and d["known_intake"][k] is not None]
            coverage[k] = len(vals)
            means[k] = round(sum(vals) / len(vals), 2) if vals else None
        def weight_window(last):
            vals = [self.day((last - timedelta(days=i)).isoformat())["morning_weight_kg"] for i in range(7)]
            vals = [v for v in vals if v is not None]
            return {"days": len(vals), "mean_kg": round(sum(vals) / len(vals), 3) if len(vals) >= 4 else None}
        current_weight = weight_window(end_date)
        previous_weight = weight_window(end_date - timedelta(days=7))
        delta = None
        if current_weight["mean_kg"] is not None and previous_weight["mean_kg"] is not None:
            delta = round(current_weight["mean_kg"] - previous_weight["mean_kg"], 3)
        return {"start": daily[0]["date"], "end": end, "calendar_days": days,
                "recorded_days": sum(d["recorded"] for d in daily),
                "complete_meal_days": sum(d["meals_complete"] for d in daily),
                "complete_day_intake_mean": means, "nutrient_coverage_days": coverage,
                "exercise_sessions": sum(d["exercise_sessions"] for d in daily),
                "exercise_minutes": round(sum(d["exercise_minutes"] for d in daily), 2),
                "weight_current_7d": current_weight, "weight_previous_7d": previous_weight,
                "weight_change_kg": delta, "auto_adjust_targets": False, "daily": daily}

    def export(self, output, fmt):
        out = Path(output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        tables = ("profile_versions", "events", "event_history", "day_status")
        snapshot = {t: [dict(r) for r in self.db.execute(f"SELECT * FROM {t}")] for t in tables}
        # All rows come from a single read transaction; do not export a torn snapshot.
        with out.open("x", encoding="utf-8-sig" if fmt == "csv" else "utf-8", newline="") as f:
            if fmt == "json":
                json.dump({"schema_version": 1, "exported_at": stamp(), "storage_mode": "local", **snapshot},
                          f, ensure_ascii=False, indent=2, allow_nan=False)
            else:
                writer = csv.writer(f)
                writer.writerow(["table", "row_json"])
                for table, rows in snapshot.items():
                    for row in rows:
                        # JSON starts with '{', preventing spreadsheet formula injection.
                        writer.writerow([table, clean_json(row)])
        return {"exported": True, "path": str(out), "contains_personal_health_data": True}

    def backup(self, output):
        out = Path(output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("xb"):
            pass
        dest = sqlite3.connect(out)
        try:
            self.db.backup(dest)
        finally:
            dest.close()
        return {"backed_up": True, "path": str(out)}


def estimate_exercise(weight, minutes, met):
    number(weight, "weight_kg", 0.01)
    number(minutes, "duration_min", 0.01, 1440)
    number(met, "MET", 1, 30)
    return {"weight_kg": weight, "duration_min": minutes, "met": met,
            "estimated_session_total_kcal": round(met * 3.5 * weight / 200 * minutes, 1),
            "estimated_above_rest_kcal": round((met - 1) * 3.5 * weight / 200 * minutes, 1),
            "source": "MET estimate; user must provide activity/intensity reference",
            "auto_add_to_food_budget": False}


def calculate_plan(age, sex, height, weight, energy, protein_per_kg=2.0, fat_share=0.25):
    number(age, "age", 18, 120)
    number(height, "height", 100, 250)
    number(weight, "weight", 20, 400)
    number(energy, "energy", 0.01)
    number(protein_per_kg, "protein_per_kg", 0.8, 2.4)
    number(fat_share, "fat_share", 0.2, 0.35)
    if sex not in ("male", "female"):
        raise JournalError("sex 必须为 male 或 female。")
    protein = round(weight * protein_per_kg / 5) * 5
    fat = round(energy * fat_share / 9 / 5) * 5
    carb = (energy - 4 * protein - 9 * fat) / 4
    if carb < 0:
        raise JournalError("所选热量不足以容纳蛋白质和脂肪目标，请复核方案。")
    ree = 10 * weight + 6.25 * height - 5 * age + (5 if sex == "male" else -161)
    return {"estimated_resting_energy_kcal": round(ree, 2), "reference_weight_kg": weight,
            "protein_per_kg_selected": protein_per_kg, "fat_share_selected": fat_share,
            "proposed_targets": {"energy_kcal": energy, "protein_g": protein, "fat_g": fat,
                                 "carb_g": round(carb, 2), "fiber_g": 25, "fruit_veg_g": 400},
            "clinical_review_or_personalization_required": True, "automatically_saved": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--store", default=os.environ.get("HEALTH_JOURNAL_HOME", "E:/HealthJournal/data"))
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("init", "record"):
        sub.add_parser(name).add_argument("--input", required=True)
    prof = sub.add_parser("profile")
    prof.add_argument("--input")
    prof.add_argument("--date")
    for name in ("get", "void", "edit"):
        x = sub.add_parser(name)
        x.add_argument("--id", required=True)
        if name != "get":
            x.add_argument("--revision", type=int, required=True)
        if name == "edit":
            x.add_argument("--input", required=True)
    for name in ("day", "complete"):
        x = sub.add_parser(name)
        x.add_argument("--date", default=today())
        if name == "complete":
            x.add_argument("--incomplete", action="store_true")
    w = sub.add_parser("week")
    w.add_argument("--end", default=today())
    w.add_argument("--days", type=int, default=7)
    x = sub.add_parser("export")
    x.add_argument("--out", required=True)
    x.add_argument("--format", choices=("json", "csv"), default="json")
    sub.add_parser("backup").add_argument("--out", required=True)
    x = sub.add_parser("estimate-exercise")
    x.add_argument("--weight", type=float, required=True)
    x.add_argument("--minutes", type=float, required=True)
    x.add_argument("--met", type=float, required=True)
    x = sub.add_parser("calculate-plan")
    for flag in ("age", "height", "weight", "energy"):
        x.add_argument("--" + flag, type=float, required=True)
    x.add_argument("--sex", choices=("male", "female"), required=True)
    x.add_argument("--protein-per-kg", type=float, default=2.0)
    x.add_argument("--fat-share", type=float, default=0.25)
    a = p.parse_args()
    j = None
    try:
        if a.command == "estimate-exercise":
            result = estimate_exercise(a.weight, a.minutes, a.met)
        elif a.command == "calculate-plan":
            result = calculate_plan(a.age, a.sex, a.height, a.weight, a.energy, a.protein_per_kg, a.fat_share)
        else:
            # Validate seed input before creating any database file.
            seed = validate_profile(read_json(a.input)) if a.command == "init" else None
            j = Journal(a.store, create=a.command == "init")
            if a.command == "init":
                result = j.set_profile(seed, initial=True)
            elif a.command == "profile":
                result = j.set_profile(read_json(a.input)) if a.input else j.profile(a.date or today())
                if result is None:
                    raise JournalError("没有对应日期的个人资料。")
            elif a.command in ("record", "edit"):
                e = read_json(a.input)
                if a.command == "edit" and e.get("id") != a.id:
                    raise JournalError("edit --id 必须与输入事件 id 一致。")
                result = j.record(e, getattr(a, "revision", None))
            elif a.command == "get":
                result = j.get(a.id)
            elif a.command == "void":
                result = j.void(a.id, a.revision)
            elif a.command == "day":
                result = j.day(a.date)
            elif a.command == "complete":
                result = j.complete(a.date, not a.incomplete)
            elif a.command == "week":
                result = j.week(a.end, a.days)
            elif a.command == "export":
                with j.db:
                    j.db.execute("BEGIN")
                    result = j.export(a.out, a.format)
            else:
                result = j.backup(a.out)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (JournalError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    finally:
        if j:
            j.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
