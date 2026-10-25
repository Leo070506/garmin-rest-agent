import random
from datetime import date, datetime, time, timedelta, timezone

from .normalize import normalize_day


def demo_days(end: date, tz, count=50):
    rng = random.Random(127)
    rows = []
    for i in range(count):
        day = end - timedelta(days=count - 1 - i)
        hours = 7.55 + rng.uniform(-0.55, 0.6)
        if i in {count - 5, count - 4}:
            hours -= 1.4
        wake = datetime.combine(day, time(7, 30), tzinfo=tz) + timedelta(minutes=rng.randrange(-20, 21))
        start = wake - timedelta(hours=hours + 0.15)
        def ms(dt):
            return int(dt.astimezone(timezone.utc).timestamp() * 1000)
        acts = []
        if day.weekday() in {1, 3, 5}:
            minutes = 35 + rng.randrange(0, 20)
            acts.append({"activityId": i + 1, "activityName": "PRIVATE NAME NOT EXPORTED",
                         "startTimeLocal": day.isoformat() + " 17:00:00", "duration": minutes * 60,
                         "distance": minutes * 150, "averageHR": 142,
                         "activityType": {"typeKey": "running"}, "startLatitude": 0.123})
        payload = {"sleep": {"dailySleepDTO": {
            "sleepTimeSeconds": int(hours * 3600), "sleepStartTimestampGMT": ms(start),
            "sleepEndTimestampGMT": ms(wake), "sleepScores": {"overall": {"value": round(hours * 10 + 5)}},
            "deepSleepSeconds": 4200, "remSleepSeconds": 5700}},
            "stats": {"restingHeartRate": 48 + rng.randrange(-2, 3),
                      "totalSteps": rng.randrange(5000, 13000), "averageStressLevel": rng.randrange(22, 38)},
            "hrv": {"hrvSummary": {"lastNightAvg": rng.randrange(55, 72)}},
            "body_battery": [{"date": day.isoformat(), "charged": 55, "drained": 60,
                              "bodyBatteryValuesArray": [[0, 0, 30], [0, 0, 90]]}],
            "activities": acts}
        status = {k: "ok" for k in ("sleep", "stats", "hrv", "stress", "body_battery", "activities")}
        row = normalize_day(day, payload, tz, "synthetic", status)
        row["is_demo"] = True
        rows.append(row)
    return rows
