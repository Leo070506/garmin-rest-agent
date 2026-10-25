"""Allowlisted import of visible website measurements. Never read browser credentials."""
from datetime import date, datetime
from urllib.parse import urlsplit

from .normalize import normalize_day, number
from .preferences import TOPICS, merge_selected
from .storage import read_days, save_day

CONNECT_URLS = {"cn": "https://connect.garmin.cn/modern/", "global": "https://connect.garmin.com/modern/"}
MEASUREMENTS = {
    "sleep_hours": ("sleep", 0.01, 24), "sleep_score": ("sleep", 0, 100),
    "deep_minutes": ("sleep", 0, 1440), "rem_minutes": ("sleep", 0, 1440),
    "resting_hr": ("recovery", 20, 150), "hrv_ms": ("recovery", 1, 400),
    "stress_mean": ("recovery", 0, 100), "body_battery_max": ("recovery", 0, 100),
    "body_battery_min": ("recovery", 0, 100), "steps": ("steps", 0, 200000),
}


def connection_plan(cfg):
    return {"region": cfg.region, "collection_method": cfg.source, "url": CONNECT_URLS[cfg.region],
            "browser_session": "not_checked_by_cli", "connected": None,
            "note": "由本人在官方网页登录后，Codex 需看到带日期的数据才能确认网页可读。"
                    "此命令不验证登录，也不导出浏览器凭据。",
            "system_scheduler_supported": cfg.source in {"community", "personal"}}


def _stamp(value):
    if value is None:
        return None
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("网页睡眠时间必须包含日期和时区；不要推测跨午夜日期。")
    return stamp.timestamp() * 1000


def _prepare(raw, cfg):
    day = date.fromisoformat(raw["date"])
    if raw.get("date_confirmed") is not True:
        raise ValueError("需先从网页确认记录日期。")
    url = urlsplit(raw["page_url"])
    if (url.scheme != "https" or url.hostname != urlsplit(CONNECT_URLS[cfg.region]).hostname
            or url.username or url.password or url.port not in {None, 443}
            or not url.path.startswith(("/modern/", "/app/")) or url.query or url.fragment):
        raise ValueError("网页来源须为所选区域的官方 Connect 页面，且不带查询、片段或凭据。")
    topics = raw.get("topics")
    if not isinstance(topics, list) or not topics or any(t not in TOPICS for t in topics):
        raise ValueError("网页记录需要明确的已读取主题。")
    if len(set(topics)) != len(topics):
        raise ValueError("网页主题不能重复。")
    values = raw.get("measurements", {})
    measured = {}
    for key, (topic, low, high) in MEASUREMENTS.items():
        value = values.get(key)
        if value is None or topic not in topics:
            continue
        valid = number(value, low, high)
        if valid is None:
            raise ValueError(f"网页指标 {key} 的值或单位无效；缺失请用 null。")
        measured[key] = valid
    dto = {"sleepTimeSeconds": measured.get("sleep_hours", 0) * 3600 or None,
           "sleepScores": {"overall": {"value": measured.get("sleep_score")}}}
    for key, dest in [("deep_minutes", "deepSleepSeconds"), ("rem_minutes", "remSleepSeconds")]:
        dto[dest] = measured[key] * 60 if key in measured else None
    if "sleep" in topics:
        dto.update(sleepStartTimestampGMT=_stamp(values.get("sleep_start")),
                   sleepEndTimestampGMT=_stamp(values.get("sleep_end")))
    activities = []
    activity_items = raw.get("activities", []) if set(topics) & {"activity", "training"} else []
    for index, item in enumerate(activity_items):
        duration = number(item.get("duration_min"), 0, 10080)
        distance = number(item.get("distance_km"), 0, 10000)
        activities.append({"activityId": index + 1, "startTimeLocal": day.isoformat(),
                           "activityType": {"typeKey": item.get("type", "other")},
                           "duration": duration * 60 if duration is not None else None,
                           "distance": distance * 1000 if distance is not None else None,
                           "averageHR": number(item.get("average_hr"), 20, 250)})
    payload = {"sleep": {"dailySleepDTO": dto},
               "stats": {"restingHeartRate": measured.get("resting_hr"),
                         "averageStressLevel": measured.get("stress_mean"), "totalSteps": measured.get("steps")},
               "hrv": {"hrvSummary": {"lastNightAvg": measured.get("hrv_ms")}}, "activities": activities}
    status = {"sleep": "ok" if "sleep" in topics else "not_requested",
              "stats": "ok" if set(topics) & {"recovery", "steps"} else "not_requested",
              "hrv": "ok" if "hrv_ms" in measured else "missing",
              "activities": "ok" if raw.get("activities_complete") is True else "missing"}
    row = normalize_day(day, payload, cfg.tz, f"browser:{cfg.region}", status)
    row["body_battery"].update(max=measured.get("body_battery_max"), min=measured.get("body_battery_min"))
    row["warnings"].append("由 Codex 从网页可见内容读取，可能存在缺项或抄录误差；不是官方 API 授权。")
    return row, topics


def import_browser(packet, cfg):
    if cfg.source != "browser":
        raise ValueError('网页导入需要独立的 source="browser" 配置。')
    if packet.get("schema_version") != 1 or packet.get("region") != cfg.region:
        raise ValueError("网页数据版本或区域与配置不符。")
    days = packet.get("days")
    if not isinstance(days, list) or not days:
        raise ValueError("网页数据包需要非空 days。")
    prepared = [_prepare(raw, cfg) for raw in days]
    root = cfg.path("data_dir") / cfg.region
    existing = {r["date"]: r for r in read_days(root, date.min, date.max)}
    if any(existing.get(row["date"], {}).get("is_demo") for row, _ in prepared):
        raise ValueError("网页数据不能覆盖合成示例，请使用独立目录。")
    for row, topics in prepared:
        existing[row["date"]] = merge_selected(existing.get(row["date"], {}), row, topics)
    for day in {row["date"] for row, _ in prepared}:
        save_day(root, existing[day])
    return {"imported_records": len(prepared), "source": f"browser:{cfg.region}",
            "note": "已保存网页可见指标；此结果不验证后续浏览器会话是否仍有效。"}
