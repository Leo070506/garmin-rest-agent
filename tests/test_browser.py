import copy
import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from garmin_rest_agent.browser import connection_plan, import_browser
from garmin_rest_agent.cli import main
from garmin_rest_agent.config import Config, load_config
from garmin_rest_agent.sources import make_source
from garmin_rest_agent.storage import read_days


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("GARMIN_REST_TEST_TMP"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = Config(root=self.root, source="browser")
        self.packet = {"schema_version": 1, "region": "cn", "days": [{
            "date": "2026-10-25", "date_confirmed": True,
            "page_url": "https://connect.garmin.cn/modern/", "topics": ["sleep"],
            "measurements": {"sleep_hours": 7.5, "sleep_score": 82}}]}

    def rows(self):
        return read_days(self.cfg.path("data_dir") / "cn", date.min, date.max)

    def test_plan_is_regional_and_never_claims_login_verified(self):
        plan = connection_plan(self.cfg)
        self.assertIn("connect.garmin.cn", plan["url"])
        self.assertIsNone(plan["connected"])
        self.assertFalse(plan["system_scheduler_supported"])
        self.assertIn("connect.garmin.com", connection_plan(replace(self.cfg, region="global"))["url"])

    def test_init_browser_and_import_can_report_without_sdk_or_credentials(self):
        cfg = self.root / "config.toml"
        packet = self.root / "readings.json"
        packet.write_text(json.dumps(self.packet), encoding="utf-8")
        self.assertEqual(main(["--config", str(cfg), "init", "--source", "browser"]), 0)
        self.assertEqual(load_config(cfg).source, "browser")
        self.assertEqual(main(["--config", str(cfg), "import-browser", str(packet)]), 0)
        self.assertEqual(main(["--config", str(cfg), "report", "--topics", "sleep",
                              "--as-of", "2026-10-25"]), 0)
        evidence = json.loads((self.root / "reports/morning-2026-10-25/evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["metrics"]["sleep_hours"]["mean"], 7.5)
        self.assertEqual(evidence["sources"], ["browser:cn"])
        self.assertTrue(any("转录" in value for value in evidence["limitations"]))

    def test_private_text_and_urls_are_not_cached(self):
        raw = self.packet["days"][0]
        raw.update(email="private@example.com", cookies="secret-cookie", activityName="private-title")
        raw["activities"] = [{"type": "running", "duration_min": 30}]
        raw["measurements"].update(resting_hr=50, accountId="private-account")
        import_browser(self.packet, self.cfg)
        row = self.rows()[0]
        self.assertEqual(row["sleep"]["hours"], 7.5)
        self.assertIsNone(row["resting_hr"])
        self.assertEqual(row["activities"], [])
        cached = json.dumps(row)
        for text in ["private", "secret-cookie", "https://"]:
            self.assertNotIn(text, cached)

    def test_wrong_domain_region_and_unconfirmed_date_do_not_write(self):
        for url in ["https://connect.garmin.com/modern/", "https://connect.garmin.cn.evil.test/modern/",
                    "http://connect.garmin.cn/modern/", "https://connect.garmin.cn/modern/?token=secret"]:
            packet = copy.deepcopy(self.packet)
            packet["days"][0]["page_url"] = url
            with self.assertRaises(ValueError):
                import_browser(packet, self.cfg)
        self.packet["days"][0]["date_confirmed"] = False
        with self.assertRaises(ValueError):
            import_browser(self.packet, self.cfg)
        self.assertEqual(self.rows(), [])

    def test_batch_is_validated_before_any_cache_write(self):
        self.packet["days"].append(dict(self.packet["days"][0], date="2026-10-24", date_confirmed=False))
        with self.assertRaises(ValueError):
            import_browser(self.packet, self.cfg)
        self.assertEqual(self.rows(), [])

    def test_merges_different_webpages_without_erasing_sleep(self):
        import_browser(self.packet, self.cfg)
        self.packet["days"][0].update(topics=["steps"], measurements={"steps": 0})
        import_browser(self.packet, self.cfg)
        row = self.rows()[0]
        self.assertEqual(row["sleep"]["hours"], 7.5)
        self.assertEqual(row["steps"], 0)
        self.assertIsNone(row["resting_hr"])

    def test_incomplete_activity_list_is_never_known_empty_day(self):
        self.packet["days"][0].update(topics=["activity"], measurements={}, activities=[])
        import_browser(self.packet, self.cfg)
        self.assertEqual(self.rows()[0]["status"]["activities"], "missing")
        self.packet["days"][0]["activities_complete"] = True
        import_browser(self.packet, self.cfg)
        self.assertEqual(self.rows()[0]["status"]["activities"], "ok")

    def test_browser_cannot_silently_use_an_sdk_session(self):
        with self.assertRaisesRegex(ValueError, "网页模式"):
            make_source(self.cfg)
        with self.assertRaises(ValueError):
            import_browser(self.packet, replace(self.cfg, source="community"))

    def test_wrong_units_and_ambiguous_time_are_rejected(self):
        self.packet["days"][0]["measurements"]["sleep_hours"] = 450
        with self.assertRaises(ValueError):
            import_browser(self.packet, self.cfg)
        self.packet["days"][0]["measurements"] = {"sleep_start": "2026-10-24T23:00:00"}
        with self.assertRaises(ValueError):
            import_browser(self.packet, self.cfg)


if __name__ == "__main__":
    unittest.main()
