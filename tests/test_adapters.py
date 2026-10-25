import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from garmin_rest_agent.config import Config
from garmin_rest_agent.sources import CommunitySource, PersonalSource


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("GARMIN_REST_TEST_TMP"))
        self.addCleanup(self.tmp.cleanup)
        self.cfg = Config(root=Path(self.tmp.name))

    def test_personal_rejects_china_before_any_authentication(self):
        with self.assertRaisesRegex(ValueError, "中国区"):
            PersonalSource(self.cfg)

    @unittest.skipUnless(importlib.util.find_spec("garminconnect"), "optional community SDK not installed")
    def test_community_passes_china_region_and_single_attempt(self):
        from garminconnect import Garmin
        client = Mock(spec=Garmin)
        for name in ["get_sleep_data", "get_stats", "get_hrv_data", "get_stress_data"]:
            getattr(client, name).return_value = {}
        client.get_body_battery.return_value = []
        client.get_activities_by_date.return_value = []
        tokens = self.cfg.path("token_dir") / "cn"
        tokens.mkdir(parents=True)
        (tokens / "synthetic-marker").write_text("not-a-token", encoding="utf-8")
        with patch("garminconnect.Garmin", return_value=client) as constructor:
            source = CommunitySource(self.cfg)
            constructor.assert_called_once_with(is_cn=True, retry_attempts=1)
            with patch("garmin_rest_agent.sources.time.sleep"):
                payload, status = source.fetch("2026-10-25")
        self.assertEqual(status["activities"], "ok")
        self.assertEqual(payload["activities"], [])
        client.get_sleep_data.assert_called_once_with("2026-10-25")

    @unittest.skipUnless(importlib.util.find_spec("garmin_personal_api"), "optional official SDK not installed")
    def test_personal_activity_pagination(self):
        from dataclasses import replace

        from garmin_personal_api import GarminPersonalApiClient, PersonalApiAuthenticator
        cfg = replace(self.cfg, source="personal", region="global")
        auth = Mock(spec=PersonalApiAuthenticator)
        auth.base_url = "https://personal.connectapi.garmin.com"
        auth.obtain_token.return_value = SimpleNamespace(access_token="synthetic-test-token")
        context = Mock()
        context.__enter__ = Mock(return_value=auth)
        context.__exit__ = Mock(return_value=False)
        client = Mock(spec=GarminPersonalApiClient)
        client.base_url = auth.base_url
        client.get_daily_sleep.return_value = {}
        client.get_daily_summaries.return_value = []
        client.get_daily_hrv.return_value = None
        client.get_daily_body_battery.return_value = []
        client.search_activities.side_effect = [[{"activityId": x} for x in range(100)], [{"activityId": 100}]]
        with patch.dict(os.environ, {"GARMIN_PERSONAL_API_KEY": "synthetic-test-key"}), \
             patch("garmin_personal_api.PersonalApiAuthenticator", return_value=context), \
             patch("garmin_personal_api.GarminPersonalApiClient", return_value=client):
            source = PersonalSource(cfg)
            payload, status = source.fetch("2026-10-25")
        self.assertEqual(len(payload["activities"]), 101)
        self.assertEqual(status["activities"], "ok")
        self.assertEqual(client.search_activities.call_args_list[1].kwargs["start"], 100)

    @unittest.skipUnless(importlib.util.find_spec("garmin_personal_api"), "optional official SDK not installed")
    def test_personal_rejects_redirected_endpoint_before_sending_key(self):
        from dataclasses import replace
        cfg = replace(self.cfg, source="personal", region="global")
        auth = Mock()
        auth.base_url = "https://example.invalid"
        context = Mock()
        context.__enter__ = Mock(return_value=auth)
        context.__exit__ = Mock(return_value=False)
        with patch.dict(os.environ, {"GARMIN_PERSONAL_API_KEY": "synthetic-test-key"}), \
             patch("garmin_personal_api.PersonalApiAuthenticator", return_value=context):
            with self.assertRaises(RuntimeError):
                PersonalSource(cfg)
        auth.obtain_token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
