import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from garmin_rest_agent.analysis import build_evidence
from garmin_rest_agent.cli import generate, main
from garmin_rest_agent.config import Config
from garmin_rest_agent.demo import demo_days
from garmin_rest_agent.preferences import (
    Preferences,
    interactive_setup,
    load_preferences,
    merge_selected,
    requested_endpoints,
    save_preferences,
    schedule_plan,
    validate,
)
from garmin_rest_agent.report import html_report, markdown_report
from garmin_rest_agent.storage import save_day


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("GARMIN_REST_TEST_TMP"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config(root=self.root)
        self.day = date(2026, 10, 26)
        self.rows = demo_days(self.day, self.cfg.tz)

    def test_new_install_requires_onboarding_and_never_schedules_by_default(self):
        p = load_preferences(self.root)
        self.assertFalse(p.configured)
        self.assertEqual(schedule_plan(p)["jobs"], [])
        self.assertFalse(schedule_plan(p)["installed"])

    def test_multi_topic_setup_collects_relevant_times(self):
        answers = iter(["1,5", "3", "08:10", "5", "20:15", "Asia/Shanghai"])
        p = interactive_setup(Preferences(), ask=lambda _: next(answers))
        self.assertEqual(p.topics, ("sleep", "steps"))
        self.assertEqual(p.frequency, "both")
        self.assertEqual(p.weekly_day, "Friday")
        self.assertEqual([j["time"] for j in schedule_plan(p)["jobs"]], ["08:10", "20:15"])

    def test_manual_setup_does_not_ask_report_time(self):
        answers = iter(["1", "4", "Asia/Shanghai"])
        p = interactive_setup(Preferences(), ask=lambda _: next(answers))
        self.assertEqual(p.frequency, "manual")
        self.assertEqual(schedule_plan(p)["jobs"], [])

    def test_invalid_time_topic_or_duplicate_rejected(self):
        for p in [Preferences(daily_time="25:01"), Preferences(topics=()),
                  Preferences(topics=("sleep", "sleep")), Preferences(topics=("unknown",))]:
            with self.assertRaises(ValueError):
                validate(p)

    def test_persist_preferences_and_modify_only_one_field(self):
        cfg = self.root / "config.toml"
        self.assertEqual(main(["--config", str(cfg), "configure", "--topics", "sleep,steps",
                              "--frequency", "both", "--daily-time", "08:10"]), 0)
        self.assertEqual(main(["--config", str(cfg), "configure", "--daily-time", "09:15"]), 0)
        p = load_preferences(self.root)
        self.assertEqual(p.topics, ("sleep", "steps"))
        self.assertEqual(p.frequency, "both")
        self.assertEqual(p.daily_time, "09:15")
        self.assertTrue(p.configured)

    def test_configuration_does_not_touch_health_cache(self):
        data = self.root / "data" / "cn"
        save_day(data, self.rows[-1])
        path = data / f"{self.day}.json"
        before = path.read_bytes()
        self.assertEqual(main(["--config", str(self.root / "config.toml"), "configure",
                              "--topics", "sleep"]), 0)
        self.assertEqual(path.read_bytes(), before)

    def test_sleep_only_evidence_excludes_other_metrics_and_training(self):
        p = Preferences(configured=True, topics=("sleep",))
        e = build_evidence(self.rows, self.cfg, "morning", self.day, p)
        self.assertEqual(set(e["metrics"]), {"sleep_hours", "sleep_score"})
        self.assertIsNone(e["training"])
        self.assertEqual(e["deviations"], {})
        self.assertNotIn("resting_hr", e["series"][0])
        self.assertNotIn("HRV基线", "".join(e["findings"]))
        self.assertIn("每日睡眠报告", html_report(e, markdown_report(e)))

    def test_steps_only_morning_uses_yesterday_not_partial_today(self):
        self.rows[-1]["steps"] = 100
        self.rows[-2]["steps"] = 12000
        p = Preferences(topics=("steps",))
        e = build_evidence(self.rows, self.cfg, "morning", self.day, p)
        self.assertEqual(e["metrics"]["steps"]["mean"], 12000)
        self.assertEqual(e["series"][0]["steps_date"], "2026-10-25")
        self.assertLess(e["baseline"]["end"], "2026-10-25")
        self.assertNotIn("静息心率", markdown_report(e))

    def test_missing_steps_not_zero_and_real_zero_valid(self):
        p = Preferences(topics=("steps",))
        self.rows[-2]["steps"] = None
        e = build_evidence(self.rows, self.cfg, "morning", self.day, p)
        self.assertIsNone(e["metrics"]["steps"]["mean"])
        self.rows[-2]["steps"] = 0
        e = build_evidence(self.rows, self.cfg, "morning", self.day, p)
        self.assertEqual(e["metrics"]["steps"]["mean"], 0)

    def test_activity_only_report_renders_without_sleep_fields(self):
        p = Preferences(topics=("activity", "training"))
        e = build_evidence(self.rows, self.cfg, "weekly", self.day, p)
        self.assertEqual(e["metrics"], {})
        self.assertIsNotNone(e["training"])
        self.assertIn("运动记录", markdown_report(e))
        self.assertIn("运动分钟", html_report(e, markdown_report(e)))

    def test_oneoff_topic_override_does_not_change_saved_profile(self):
        p = Preferences(configured=True, topics=("sleep",), goal="sleep")
        save_preferences(self.root, p)
        for row in self.rows:
            save_day(self.cfg.path("data_dir") / "cn", row)
        folder = generate(self.cfg, "morning", self.day, topics=("steps",))
        e = json.loads((folder / "evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(e["preferences"]["topics"], ["steps"])
        self.assertEqual(load_preferences(self.root).topics, ("sleep",))

    def test_personal_sleep_target_and_report_style_reach_evidence(self):
        p = Preferences(topics=("sleep",), sleep_goal_hours=8.5, detail="detailed", goal="sleep")
        e = build_evidence(self.rows, self.cfg, "morning", self.day, p)
        self.assertEqual(e["sleep_goal_hours"], 8.5)
        self.assertEqual(e["preferences"]["detail"], "detailed")

    def test_endpoint_selection_is_minimal(self):
        self.assertEqual(requested_endpoints(("sleep",)), {"sleep"})
        self.assertEqual(requested_endpoints(("steps",)), {"stats"})
        self.assertEqual(requested_endpoints(("activity", "training")), {"activities"})

    def test_narrow_sync_preserves_all_unselected_history(self):
        previous = self.rows[-1]
        current = dict(previous, sleep={"hours": 6.5}, resting_hr=None, hrv_ms=None, activities=[], steps=None)
        merged = merge_selected(previous, current, ("sleep",))
        self.assertEqual(merged["sleep"]["hours"], 6.5)
        for key in ["resting_hr", "hrv_ms", "activities", "steps", "body_battery"]:
            self.assertEqual(merged[key], previous[key])
        self.assertEqual(previous["sleep"], self.rows[-1]["sleep"])


if __name__ == "__main__":
    unittest.main()
