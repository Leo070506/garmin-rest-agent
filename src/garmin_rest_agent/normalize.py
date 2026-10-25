"""Allowlisted normalization. Do not retain names, account IDs, GPS or raw payloads."""
import math
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def number(value, low=0, high=float("inf")):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and low <= value <= high else None


def nested(obj, *keys):
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def timestamp(value, tz: ZoneInfo):
    value = number(value, 1)
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).astimezone(tz).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def normalize_day(day: date, payload: dict, tz: ZoneInfo, source: str, status: dict) -> dict:
    sleep = payload.get("sleep") or {}
    dto = sleep.get("dailySleepDTO", {}) if isinstance(sleep, dict) else {}
    stats = payload.get("stats") or {}
    if isinstance(stats, list):
        stats = next((x for x in stats if x.get("calendarDate") == day.isoformat()), {})
    hrv = payload.get("hrv") or {}
    stress = payload.get("stress") or {}
    seconds = number(dto.get("sleepTimeSeconds"), 1, 86400)
    start = timestamp(dto.get("sleepStartTimestampGMT"), tz)
    end = timestamp(dto.get("sleepEndTimestampGMT"), tz)
    warnings = []
    if seconds and not (start and end):
        warnings.append("缺少 GMT 睡眠时间；不从 Local 毫秒字段推算，避免重复时区偏移。")
    if start and end and (datetime.fromisoformat(end) <= datetime.fromisoformat(start)):
        warnings.append("睡眠起止时间异常，已忽略时间。")
        start = end = None
    if end and datetime.fromisoformat(end).date() != day:
        warnings.append("睡眠结束日与请求日期不同；该睡眠已排除，等待重新同步。")
        seconds = None
        start = end = None
        dto = {}
    bb = payload.get("body_battery") or []
    if isinstance(bb, dict):
        bb = [bb]
    bb = next((x for x in bb if isinstance(x, dict) and x.get("date") == day.isoformat()), {})
    values = [number(x[-1], 0, 100) for x in (bb.get("bodyBatteryValuesArray") or [])
              if isinstance(x, list) and len(x) >= 2]
    values = [x for x in values if x is not None]
    acts, seen = [], set()
    for item in payload.get("activities") or []:
        if not isinstance(item, dict):
            continue
        local = item.get("startTimeLocal", "")
        if str(local)[:10] != day.isoformat():
            continue
        ident = str(item.get("activityId") or "")
        dedup = ident or (str(local), str(item.get("duration")), str(item.get("distance")))
        if dedup in seen:
            continue
        seen.add(dedup)
        duration = number(item.get("duration"), 0, 604800)
        distance = number(item.get("distance"), 0, 1e7)
        kind = nested(item, "activityType", "typeKey")
        # Unknown/free-text types never enter prompts.
        allowed = {"running", "trail_running", "treadmill_running", "cycling", "indoor_cycling",
                   "walking", "hiking", "lap_swimming", "open_water_swimming", "strength_training",
                   "yoga", "pilates", "cardio", "elliptical", "fitness_equipment", "other"}
        acts.append({"type": kind if kind in allowed else "other",
                     "duration_min": duration / 60 if duration is not None else None,
                     "distance_km": distance / 1000 if distance is not None else None,
                     "average_hr": number(item.get("averageHR"), 20, 250)})
    stress_value = number(stats.get("averageStressLevel"), 0, 100)
    if stress_value is None and isinstance(stress, dict):
        stress_value = number(stress.get("avgStressLevel"), 0, 100)
    return {
        "schema_version": 1, "date": day.isoformat(), "source": source, "is_demo": False,
        "fetched_at": datetime.now(timezone.utc).isoformat(), "status": dict(status), "warnings": warnings,
        "sleep": {"hours": round(seconds / 3600, 4) if seconds else None,
                  "score": number(nested(dto, "sleepScores", "overall", "value"), 0, 100),
                  "start": start, "end": end,
                  "deep_minutes": (number(dto.get("deepSleepSeconds"), 0, 86400) or 0) / 60
                      if number(dto.get("deepSleepSeconds"), 0, 86400) is not None else None,
                  "rem_minutes": (number(dto.get("remSleepSeconds"), 0, 86400) or 0) / 60
                      if number(dto.get("remSleepSeconds"), 0, 86400) is not None else None},
        "resting_hr": number(stats.get("restingHeartRate"), 20, 150),
        "hrv_ms": number(nested(hrv, "hrvSummary", "lastNightAvg"), 1, 400),
        "stress_mean": stress_value, "steps": number(stats.get("totalSteps"), 0, 200000),
        "body_battery": {"max": max(values) if values else None, "min": min(values) if values else None,
                         "charged": number(bb.get("charged"), 0, 500),
                         "drained": number(bb.get("drained"), 0, 500)},
        "activities": acts,
    }
