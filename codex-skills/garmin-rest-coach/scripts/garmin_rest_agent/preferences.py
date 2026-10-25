"""Local, non-secret preferences shared by the skill, reports and schedule preview."""
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from .console import ensure_utf8_console
from .storage import write_json

TOPICS = {"sleep": "睡眠", "recovery": "恢复", "activity": "日常运动", "training": "训练", "steps": "步数"}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
GOALS = {"balance": "保持健康与生活平衡", "sleep": "改善睡眠", "recovery": "改善恢复",
         "fitness": "提升体能", "race": "备赛", "move_more": "增加日常活动"}


def requested_endpoints(topics):
    required = set()
    if "sleep" in topics:
        required.add("sleep")
    if "recovery" in topics:
        required.update({"stats", "hrv", "stress", "body_battery"})
    if "steps" in topics:
        required.add("stats")
    if set(topics) & {"activity", "training"}:
        required.add("activities")
    return required


def merge_selected(previous: dict, current: dict, topics) -> dict:
    """Update requested measurements; retain every field from unselected historical topics."""
    fields = {"sleep": ("sleep",), "recovery": ("resting_hr", "hrv_ms", "stress_mean", "body_battery"),
              "steps": ("steps",), "activity": ("activities",), "training": ("activities",)}
    result = dict(previous) if previous else dict(current)
    for topic in topics:
        for key in fields[topic]:
            result[key] = current[key]
    for key in ("date", "schema_version", "fetched_at", "source", "is_demo"):
        result[key] = current[key]
    result["status"] = dict(previous.get("status", {}))
    result["status"].update({k: v for k, v in current["status"].items() if k in requested_endpoints(topics)})
    result["warnings"] = list(dict.fromkeys(previous.get("warnings", []) + current.get("warnings", [])))
    result["collected_topics"] = sorted(set(previous.get("collected_topics", ())) | set(topics))
    result["collection_at_by_topic"] = dict(previous.get("collection_at_by_topic", {}))
    result["collection_at_by_topic"].update({t: current["fetched_at"] for t in topics})
    return result


@dataclass(frozen=True)
class Preferences:
    schema_version: int = 1
    configured: bool = False
    topics: tuple[str, ...] = tuple(TOPICS)
    frequency: str = "manual"
    daily_time: str = "07:30"
    weekly_day: str = "Monday"
    weekly_time: str = "08:00"
    timezone: str = "Asia/Shanghai"
    detail: str = "brief"
    goal: str = "balance"
    sleep_goal_hours: float = 7.5


def validate(p: Preferences) -> Preferences:
    if p.schema_version != 1 or not isinstance(p.configured, bool):
        raise ValueError("偏好文件版本或 configured 无效。")
    if not p.topics or any(t not in TOPICS for t in p.topics) or len(set(p.topics)) != len(p.topics):
        raise ValueError("关注主题应为不重复的 sleep,recovery,activity,training,steps，至少选一项。")
    if p.frequency not in {"daily", "weekly", "both", "manual"}:
        raise ValueError("频率应为 daily、weekly、both 或 manual。")
    for value in (p.daily_time, p.weekly_time):
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("汇报时间必须是有效的 24 小时制 HH:mm。")
    if p.weekly_day not in WEEKDAYS or p.detail not in {"brief", "detailed"} or p.goal not in GOALS:
        raise ValueError("每周日期、报告详略或目标无效。")
    ZoneInfo(p.timezone)
    if isinstance(p.sleep_goal_hours, bool) or not 1 <= p.sleep_goal_hours <= 16:
        raise ValueError("个人睡眠目标必须在 1–16 小时之间。")
    return p


def load_preferences(root: Path, timezone="Asia/Shanghai", sleep_goal=7.5) -> Preferences:
    path = root / "preferences.json"
    if not path.exists():
        return Preferences(timezone=timezone, sleep_goal_hours=sleep_goal)
    obj = json.loads(path.read_text(encoding="utf-8"))
    obj["topics"] = tuple(obj.get("topics", ()))
    return validate(Preferences(**obj))


def save_preferences(root: Path, p: Preferences) -> None:
    write_json(root / "preferences.json", asdict(validate(p)))


def schedule_plan(p: Preferences) -> dict:
    """Preferences are a plan, never proof of actual scheduler installation."""
    jobs = []
    if p.frequency in {"daily", "both"}:
        jobs.append({"kind": "morning", "frequency": "daily", "time": p.daily_time, "timezone": p.timezone})
    if p.frequency in {"weekly", "both"}:
        jobs.append({"kind": "weekly", "frequency": "weekly", "weekday": p.weekly_day,
                     "time": p.weekly_time, "timezone": p.timezone})
    return {"preferences_configured": p.configured, "installed": False,
            "note": "仅为计划预览；修改偏好不会自动创建、修改或删除任何已有任务。", "jobs": jobs}


def interactive_setup(current: Preferences, ask=input) -> Preferences:
    """Terminal fallback; Codex should ask the same questions conversationally."""
    from dataclasses import replace
    ensure_utf8_console()
    print("佳息首次设置：可选多个主题，之后随时可以修改。")
    print("1 睡眠 / 2 恢复 / 3 日常运动 / 4 训练 / 5 步数")
    topics_text = ask("关注哪些？输入编号，用逗号分隔（回车保留当前选择）：").strip()
    topics = current.topics
    if topics_text:
        indexes = topics_text.replace("，", ",").replace(" ", ",").split(",")
        keys = tuple(TOPICS)
        if any(not x.isdigit() or not 1 <= int(x) <= len(keys) for x in indexes if x):
            raise ValueError("主题编号应为 1–5。")
        topics = tuple(dict.fromkeys(keys[int(x) - 1] for x in indexes if x))
    print("频率：1 每天 / 2 每周 / 3 每天加每周 / 4 仅手动")
    freq = ask("选择编号（回车保留）：").strip()
    mapping = {"1": "daily", "2": "weekly", "3": "both", "4": "manual"}
    if freq and freq not in mapping:
        raise ValueError("频率编号应为 1–4。")
    frequency = mapping.get(freq, current.frequency)
    daily, weekly_day, weekly = current.daily_time, current.weekly_day, current.weekly_time
    if frequency in {"daily", "both"}:
        daily = ask(f"每日汇报时间 HH:mm（{daily}）：").strip() or daily
    if frequency in {"weekly", "both"}:
        print("每周日期：1 周一至 7 周日；周报统计上一完整自然周。")
        day = ask("日期编号（回车保留）：").strip()
        if day and (not day.isdigit() or not 1 <= int(day) <= 7):
            raise ValueError("每周日期编号应为 1–7。")
        weekly_day = WEEKDAYS[int(day) - 1] if day else weekly_day
        weekly = ask(f"每周汇报时间 HH:mm（{weekly}）：").strip() or weekly
    tz = ask(f"时区（{current.timezone}）：").strip() or current.timezone
    return validate(replace(current, configured=True, topics=topics, frequency=frequency,
                            daily_time=daily, weekly_day=weekly_day, weekly_time=weekly, timezone=tz))
