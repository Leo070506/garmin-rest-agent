import math
from datetime import date, datetime, timedelta
from statistics import mean, median

from .config import Config
from .normalize import number
from .preferences import Preferences, load_preferences


def dates_between(start: date, end: date):
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def report_window(kind: str, as_of: date):
    if kind == "morning":
        return as_of, as_of
    if kind != "weekly":
        raise ValueError("kind 必须为 morning 或 weekly。")
    end = as_of - timedelta(days=as_of.weekday() + 1)
    return end - timedelta(days=6), end


def metric(row, key):
    if key == "sleep_hours":
        return number(row.get("sleep", {}).get("hours"), 0.01, 24)
    if key == "sleep_score":
        return number(row.get("sleep", {}).get("score"), 0, 100)
    if key == "body_battery_peak":
        return number(row.get("body_battery", {}).get("max"), 0, 100)
    limits = {"resting_hr": (20, 150), "hrv_ms": (1, 400), "stress_mean": (0, 100), "steps": (0, 200000)}
    return number(row.get(key), *limits[key])


def summary(rows, key):
    vals = [v for row in rows if (v := metric(row, key)) is not None]
    return {"mean": round(mean(vals), 2) if vals else None,
            "median": round(median(vals), 2) if vals else None, "n": len(vals)}


def training(rows, expected):
    known = [r for r in rows if r.get("status", {}).get("activities") == "ok"]
    items = [a for r in known for a in r.get("activities", [])]
    durations = [number(a.get("duration_min"), 0, 10080) for a in items]
    complete = len(known) == expected and all(v is not None for v in durations)
    return {"known_days": len(known), "expected_days": expected, "complete": complete,
            "activity_count": len(items),
            "minutes_recorded": round(sum(x for x in durations if x is not None), 1),
            "distance_km_recorded": round(sum(number(a.get("distance_km"), 0, 10000) or 0
                                              for a in items), 2),
            "active_days": sum(bool(r.get("activities")) for r in known)}


def timing_variation(rows, tz):
    """Circular timing avoids treating 23:50 and 00:10 as 23 hours apart."""
    vals = []
    for r in rows:
        value = r.get("sleep", {}).get("start")
        if value:
            try:
                stamp = datetime.fromisoformat(value)
                if stamp.tzinfo is None:
                    continue
                stamp = stamp.astimezone(tz)
                vals.append(stamp.hour * 60 + stamp.minute)
            except ValueError:
                pass
    if len(vals) < 3:
        return {"n": len(vals), "mean_absolute_deviation_minutes": None}
    angles = [v / 1440 * 2 * math.pi for v in vals]
    center = math.atan2(mean(math.sin(a) for a in angles), mean(math.cos(a) for a in angles))
    minutes = center / (2 * math.pi) * 1440 % 1440
    deviation = mean(abs((v - minutes + 720) % 1440 - 720) for v in vals)
    return {"n": len(vals), "mean_absolute_deviation_minutes": round(deviation, 1)}


def build_evidence(rows: list[dict], cfg: Config, kind: str, as_of: date,
                   preferences: Preferences | None = None) -> dict:
    p = preferences or load_preferences(cfg.root, cfg.timezone, cfg.sleep_goal_hours)
    selected = set(p.topics)
    start, end = report_window(kind, as_of)
    context_start = as_of - timedelta(days=1) if kind == "morning" else start
    context_end = context_start if kind == "morning" else end
    by_date = {r["date"]: r for r in rows}
    target = [by_date[d.isoformat()] for d in dates_between(start, end) if d.isoformat() in by_date]
    # Baseline precedes every focal day, including yesterday's steps/activity in a morning report.
    baseline_end = min(start, context_start) - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=cfg.baseline_days - 1)
    baseline = [r for r in rows if baseline_start.isoformat() <= r["date"] <= baseline_end.isoformat()]
    previous_start, previous_end = start - timedelta(days=7), start - timedelta(days=1)
    previous = [r for r in rows if previous_start.isoformat() <= r["date"] <= previous_end.isoformat()]
    context = [r for r in rows if context_start.isoformat() <= r["date"] <= context_end.isoformat()]
    keys = []
    if "sleep" in selected:
        keys += ["sleep_hours", "sleep_score"]
    if "recovery" in selected:
        keys += ["resting_hr", "hrv_ms", "stress_mean", "body_battery_peak"]
    if "steps" in selected:
        keys.append("steps")
    measurements = {key: summary(context if key == "steps" else target, key) for key in keys}
    references = {key: summary(baseline, key) for key in keys}
    expected = len(dates_between(start, end))
    current_training = training(context, 1 if kind == "morning" else 7)
    prior_training = training(previous, 7)
    findings = []
    actions = []
    coverage = {k: {"observed": measurements[k]["n"], "expected": expected} for k in keys}
    sleep_avg = measurements.get("sleep_hours", {}).get("mean")
    if "sleep" in selected and sleep_avg is None:
        findings.append("当前范围缺少有效睡眠记录，无法判断睡眠是否充足；缺失不等于没有睡觉。")
        actions.append("先确认手表已同步且有昨晚睡眠记录，再重新生成报告。")
    elif "sleep" in selected:
        gap = round(p.sleep_goal_hours - sleep_avg, 2)
        findings.append(f"有效记录的平均睡眠为 {sleep_avg:.2f} 小时，个人目标为 {p.sleep_goal_hours:.2f} 小时。")
        if gap > 0:
            actions.append(f"优先为睡眠多留约 {round(gap * 60)} 分钟；这是与个人目标的差额，不是精确睡眠债。")
    deviations = {}
    for key in ("resting_hr", "hrv_ms") if "recovery" in selected else ():
        current = measurements[key]["mean"]
        ref = references[key]
        enough = ref["n"] >= cfg.minimum_baseline_samples
        delta = round(current - ref["median"], 2) if current is not None and enough else None
        relative = round(delta / ref["median"] * 100, 1) if delta is not None and ref["median"] else None
        deviations[key] = {"delta_from_baseline_median": delta, "percent": relative,
                           "baseline_sufficient": enough}
        if not enough:
            findings.append(f"{'静息心率' if key == 'resting_hr' else 'HRV'}基线只有 {ref['n']} 天，暂不作个人趋势判断。")
    hrv_drop = deviations.get("hrv_ms", {}).get("percent")
    hr_up = deviations.get("resting_hr", {}).get("delta_from_baseline_median")
    if hrv_drop is not None and hrv_drop <= -15:
        findings.append(f"HRV 比此前个人基线中位数低 {abs(hrv_drop):.1f}%；这是观察信号，不能据此诊断或判定过度训练。")
    if hr_up is not None and hr_up >= 5:
        findings.append(f"静息心率比此前个人基线中位数高 {hr_up:.1f} 次/分，建议结合体感和连续记录观察。")
    if (hrv_drop is not None and hrv_drop <= -15) or (hr_up is not None and hr_up >= 5):
        actions.append("今天先评估主观疲劳；若同时感觉疲惫，可把高强度训练换为轻松活动，之后再复查趋势。")
    volume_change = None
    activity_selected = bool(selected & {"activity", "training"})
    if activity_selected and kind == "weekly" and current_training["complete"] and prior_training["complete"]:
        prior = prior_training["minutes_recorded"]
        if prior > 0:
            volume_change = round((current_training["minutes_recorded"] / prior - 1) * 100, 1)
            findings.append(f"记录到的运动时长较前一周变化 {volume_change:+.1f}%；时长不等于生理训练负荷。")
    if activity_selected and not current_training["complete"]:
        findings.append("活动记录覆盖不完整，运动总量仅代表已取得的记录，不能推断其余日期是休息日。")
    if "steps" in selected:
        steps = measurements["steps"]
        if steps["n"]:
            findings.append(f"白天活动范围内有效记录的平均步数为 {steps['mean']:.0f} 步（{steps['n']} 天）。")
        else:
            findings.append("未取得本期步数记录；不把缺失记为零步。")
    if activity_selected and not findings:
        findings.append(f"本期已取得 {current_training['activity_count']} 次运动记录、"
                        f"{current_training['minutes_recorded']:.1f} 分钟。")
    if not actions:
        actions.append("先关注连续记录与自己的目标是否一致，再决定是否调整作息或活动安排。")
    series = []
    for d in dates_between(start, end):
        r = by_date.get(d.isoformat(), {})
        record = {"date": d.isoformat(), **{key: metric(r, key) for key in keys}}
        if kind == "morning" and "steps" in selected:
            record["steps"] = metric(by_date.get(context_start.isoformat(), {}), "steps")
            record["steps_date"] = context_start.isoformat()
        if activity_selected:
            active_date = context_start if kind == "morning" else d
            active = by_date.get(active_date.isoformat(), {})
            t = training([active] if active else [], 1)
            record["activity_minutes"] = t["minutes_recorded"] if t["complete"] else None
        series.append(record)
    relevant = target + context + baseline
    demos = {r.get("is_demo", False) for r in relevant}
    if len(demos) > 1:
        raise ValueError("检测到示例与真实数据混用；请使用独立数据目录。")
    collected = []
    collected_rows = (target if selected & {"sleep", "recovery"} else []) + \
                     (context if selected & {"activity", "training", "steps"} else [])
    for r in collected_rows:
        try:
            stamp = datetime.fromisoformat(r.get("fetched_at", ""))
            if stamp.tzinfo is not None:
                collected.append(stamp)
        except ValueError:
            continue
    return {
        "schema_version": 1, "kind": kind, "as_of": as_of.isoformat(), "timezone": cfg.timezone,
        "is_demo": True in demos, "period": {"start": start.isoformat(), "end": end.isoformat()},
        "day_context": {"start": context_start.isoformat(), "end": context_end.isoformat()},
        "sleep_date_convention": "睡眠按醒来日期归档；晨报睡眠为昨晚至今早，白天活动为昨天。",
        "latest_collection_at": max(collected).isoformat() if collected else None,
        "sources": sorted({r.get("source", "unknown") for r in relevant}),
        "preferences": {"topics": list(p.topics), "detail": p.detail, "goal": p.goal,
                        "configured": p.configured},
        "baseline": {"start": baseline_start.isoformat(), "end": baseline_end.isoformat(),
                     "minimum_samples": cfg.minimum_baseline_samples, "metrics": references},
        "metrics": measurements, "coverage": coverage, "deviations": deviations,
        "training": current_training if activity_selected else None,
        "previous_week_training": prior_training if kind == "weekly" and activity_selected else None,
        "training_minutes_change_pct": volume_change,
        "bedtime_regularity": timing_variation(target, cfg.tz) if "sleep" in selected else None,
        "sleep_goal_hours": p.sleep_goal_hours if "sleep" in selected else None, "series": series,
        "findings": findings, "suggested_actions": actions,
        "limitations": ["手表数据为估计值，记录完整性受佩戴和同步情况影响。",
                        "采集时间表示本地工具取得数据的时间，不代表手表最后同步时间；未同步的记录不会自动出现。"]
            + (["本报告含网页可见数值的转录，可能有页面缺项或抄录误差；不是官方 API 授权。"]
               if any(r.get("source", "").startswith("browser:") for r in relevant) else [])
            + (["睡眠阶段和分数不等同于临床检查，不用于诊断。"] if "sleep" in selected else [])
            + (["比较使用此前独立的个人基线，不用他人的 HRV 或静息心率作为优劣标准。"]
               if "recovery" in selected else [])
            + (["没有运动强度分区及完整训练负荷，因此不判断训练计划是否最优。"]
               if activity_selected else []),
    }
