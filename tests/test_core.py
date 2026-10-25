import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from garmin_rest_agent.analysis import build_evidence, report_window, timing_variation, training
from garmin_rest_agent.cli import main
from garmin_rest_agent.config import Config, load_config
from garmin_rest_agent.demo import demo_days
from garmin_rest_agent.normalize import normalize_day, number
from garmin_rest_agent.report import html_report, markdown_report
from garmin_rest_agent.sources import checked_call
from garmin_rest_agent.storage import project_lock, read_days, save_day


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("GARMIN_REST_TEST_TMP"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config(root=self.root)
        self.today = date(2026, 10, 26)
        self.rows = demo_days(self.today, ZoneInfo("Asia/Shanghai"))

    def test_morning_uses_wake_date_and_previous_day_activity(self):
        e = build_evidence(self.rows, self.cfg, "morning", self.today)
        self.assertEqual(e["period"]["start"], "2026-10-26")
        self.assertEqual(e["day_context"]["start"], "2026-10-25")

    def test_weekly_always_previous_complete_monday_sunday(self):
        self.assertEqual(report_window("weekly", date(2026, 10, 26)),
                         (date(2026, 10, 19), date(2026, 10, 25)))
        self.assertEqual(report_window("weekly", date(2026, 10, 25)),
                         (date(2026, 10, 12), date(2026, 10, 18)))

    def test_timezone_uses_gmt_once(self):
        start = datetime(2026, 10, 24, 16, tzinfo=timezone.utc)
        end = start + timedelta(hours=8)
        raw = {"sleep": {"dailySleepDTO": {"sleepTimeSeconds": 28800,
               "sleepStartTimestampGMT": start.timestamp() * 1000,
               "sleepEndTimestampGMT": end.timestamp() * 1000,
               "sleepStartTimestampLocal": (start.timestamp() + 28800) * 1000}}}
        r = normalize_day(date(2026, 10, 25), raw, self.cfg.tz, "test", {})
        self.assertEqual(r["sleep"]["start"], "2026-10-25T00:00:00+08:00")
        self.assertEqual(r["sleep"]["hours"], 8)

    def test_stale_sleep_excluded_when_wake_date_mismatch(self):
        raw = {"sleep": {"dailySleepDTO": {"sleepTimeSeconds": 28800,
               "sleepEndTimestampGMT": datetime(2026, 10, 24, tzinfo=timezone.utc).timestamp() * 1000}}}
        r = normalize_day(self.today, raw, self.cfg.tz, "test", {})
        self.assertIsNone(r["sleep"]["hours"])

    def test_invalid_and_sentinel_numbers_are_missing_but_zero_stress_valid(self):
        for v in [-1, float("nan"), float("inf"), True, "70"]:
            self.assertIsNone(number(v))
        r = normalize_day(self.today, {"stats": {"averageStressLevel": 0, "restingHeartRate": -1}},
                          self.cfg.tz, "test", {})
        self.assertEqual(r["stress_mean"], 0)
        self.assertIsNone(r["resting_hr"])

    def test_never_substitute_weekly_hrv_for_last_night(self):
        r = normalize_day(self.today, {"hrv": {"hrvSummary": {"weeklyAvg": 75}}},
                          self.cfg.tz, "test", {})
        self.assertIsNone(r["hrv_ms"])

    def test_activity_duplicates_and_identity_fields_removed(self):
        act = {"activityId": 7, "startTimeLocal": "2026-10-26 17:00:00", "duration": 1800,
               "distance": 5000, "activityName": "private", "startLatitude": 31.0,
               "activityType": {"typeKey": "running"}}
        r = normalize_day(self.today, {"activities": [act, act]}, self.cfg.tz, "test", {})
        self.assertEqual(len(r["activities"]), 1)
        self.assertNotIn("private", json.dumps(r))
        self.assertNotIn("Latitude", json.dumps(r))

    def test_baseline_excludes_entire_target_week(self):
        e = build_evidence(self.rows, self.cfg, "weekly", self.today)
        changed = [dict(r, resting_hr=120) if r["date"] >= "2026-10-19" else r for r in self.rows]
        e2 = build_evidence(changed, self.cfg, "weekly", self.today)
        self.assertEqual(e["baseline"], e2["baseline"])
        self.assertNotEqual(e["metrics"]["resting_hr"], e2["metrics"]["resting_hr"])

    def test_missing_day_not_zero_sleep(self):
        rows = [r for r in self.rows if r["date"] != "2026-10-25"]
        e = build_evidence(rows, self.cfg, "weekly", self.today)
        self.assertEqual(e["metrics"]["sleep_hours"]["n"], 6)
        self.assertGreater(e["metrics"]["sleep_hours"]["mean"], 6)
        self.assertIsNone(e["series"][-1]["sleep_hours"])
        self.assertFalse(e["training"]["complete"])
        self.assertIsNone(e["training_minutes_change_pct"])

    def test_successful_empty_activity_is_known_zero(self):
        result = training([{"status": {"activities": "ok"}, "activities": []}], 1)
        self.assertTrue(result["complete"])
        self.assertEqual(result["minutes_recorded"], 0)
        self.assertFalse(training([{"status": {"activities": "missing"}, "activities": []}], 1)["complete"])

    def test_insufficient_baseline_does_not_create_recovery_alarm(self):
        rows = self.rows[-2:]
        e = build_evidence(rows, self.cfg, "morning", self.today)
        self.assertIsNone(e["deviations"]["hrv_ms"]["percent"])
        self.assertFalse(e["deviations"]["hrv_ms"]["baseline_sufficient"])

    def test_midnight_bedtimes_use_circular_distance(self):
        rows = [{"sleep": {"start": f"2026-10-24T{t}:00+08:00"}} for t in ["23:50", "00:10", "00:00"]]
        result = timing_variation(rows, self.cfg.tz)
        self.assertLess(result["mean_absolute_deviation_minutes"], 10)

    def test_demo_and_real_rows_cannot_mix(self):
        self.rows[-1]["is_demo"] = False
        with self.assertRaises(ValueError):
            build_evidence(self.rows, self.cfg, "morning", self.today)

    def test_training_zero_previous_week_no_division_by_zero(self):
        for r in self.rows:
            if "2026-10-12" <= r["date"] <= "2026-10-18":
                r["activities"] = []
        e = build_evidence(self.rows, self.cfg, "weekly", self.today)
        self.assertIsNone(e["training_minutes_change_pct"])

    def test_untrusted_ai_html_is_rendered_as_text(self):
        e = build_evidence(self.rows, self.cfg, "weekly", self.today)
        rendered = html_report(e, markdown_report(e, '<script>alert("x")</script>'))
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_auth_and_rate_limit_abort_without_retry(self):
        class Limited(Exception):
            status_code = 429
        calls = []
        def call():
            calls.append(1)
            raise Limited()
        with self.assertRaises(RuntimeError):
            checked_call(call)
        self.assertEqual(len(calls), 1)

    def test_unsupported_endpoint_is_missing(self):
        class Missing(Exception):
            status_code = 404
        def call():
            raise Missing()
        self.assertEqual(checked_call(call), (None, "unavailable"))

    def test_atomic_storage_replaces_and_rejects_mismatched_date(self):
        save_day(self.root, self.rows[-1])
        row = dict(self.rows[-1], resting_hr=52)
        save_day(self.root, row)
        self.assertEqual(read_days(self.root, self.today, self.today)[0]["resting_hr"], 52)
        bad = dict(row, date="2026-10-25")
        (self.root / "2026-10-26.json").write_text(json.dumps(bad), encoding="utf-8")
        with self.assertRaises(ValueError):
            read_days(self.root, self.today, self.today)

    def test_locks_exclude_concurrent_runs(self):
        with project_lock(self.root):
            with self.assertRaises(ValueError):
                with project_lock(self.root):
                    pass
        self.assertFalse((self.root / ".run.lock").exists())

    def test_config_paths_resolve_relative_to_config(self):
        p = self.root / "config.toml"
        p.write_text('source="files"\ntimezone="Asia/Shanghai"\n', encoding="utf-8")
        cfg = load_config(p)
        self.assertEqual(cfg.path("data_dir"), (self.root / "data").resolve())

    def test_cli_init_succeeds_with_chinese_output_under_legacy_windows_encoding(self):
        cfg = self.root / "legacy-console" / "config.toml"
        env = dict(os.environ, PYTHONUTF8="0", PYTHONIOENCODING="cp1252")
        process = subprocess.run([sys.executable, "-m", "garmin_rest_agent", "--config", str(cfg),
                                  "init", "--source", "browser"], env=env, capture_output=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", errors="replace"))
        self.assertTrue(cfg.is_file())
        self.assertIn("已创建", process.stdout.decode("utf-8"))

    def test_cli_offline_demo_end_to_end_and_no_cloud(self):
        destination = self.root / "demo"
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network forbidden")):
            self.assertEqual(main(["demo", "--output", str(destination)]), 0)
        for kind in ("morning", "weekly"):
            folder = destination / "reports" / f"{kind}-2026-10-26"
            evidence = json.loads((folder / "evidence.json").read_text(encoding="utf-8"))
            self.assertTrue(evidence["is_demo"])
            self.assertTrue((folder / "report.html").is_file())
            self.assertTrue((folder / "agent-prompt.md").is_file())


if __name__ == "__main__":
    unittest.main()
