import json
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from garmin_rest_agent.analysis import build_evidence
from garmin_rest_agent.cli import generate
from garmin_rest_agent.codex import launch_arguments, narrate
from garmin_rest_agent.config import Config
from garmin_rest_agent.demo import demo_days
from garmin_rest_agent.storage import save_day


class CodexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("GARMIN_REST_TEST_TMP"))
        self.addCleanup(self.tmp.cleanup)
        self.cfg = Config(root=Path(self.tmp.name))
        self.as_of = date(2026, 10, 26)
        self.rows = demo_days(self.as_of, self.cfg.tz)
        self.evidence = build_evidence(self.rows, self.cfg, "morning", self.as_of)
        self.folder = self.cfg.root / "reports"
        self.folder.mkdir()

    def test_codex_arguments_inherit_model_and_keep_readonly_sandbox(self):
        args = launch_arguments("codex.exe", self.folder, self.folder / "out.md")
        self.assertIn("read-only", args)
        self.assertIn("--ephemeral", args)
        self.assertNotIn("--model", args)
        self.assertNotIn("--yolo", args)
        self.assertEqual(args[-1], "-")

    def test_successful_cli_writes_separate_report_without_leaking_raw_data(self):
        seen = {}
        def run(args, prompt, workspace, timeout):
            seen.update(input=prompt, cwd=workspace)
            output = Path(args[args.index("--output-last-message") + 1])
            output.write_text("# 今日观察\n\n合成示例：优先观察连续睡眠记录。", encoding="utf-8")
            return 0
        with patch("garmin_rest_agent.codex.shutil.which", return_value="codex.exe"), \
             patch("garmin_rest_agent.codex.invoke", side_effect=run):
            path = narrate(self.cfg, self.evidence, self.folder)
        self.assertTrue(path.is_file())
        self.assertTrue((self.folder / "agent-report.html").is_file())
        self.assertNotIn("PRIVATE NAME", seen["input"])
        self.assertNotIn("startLatitude", seen["input"])
        self.assertNotIn("tokens", str(seen["cwd"]))
        self.assertEqual(json.loads((self.folder / "codex-generation.json").read_text())["method"], "codex-exec")

    def test_missing_codex_does_not_erase_base_report(self):
        for r in self.rows:
            save_day(self.cfg.path("data_dir") / "cn", r)
        with patch("garmin_rest_agent.codex.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "找不到"):
                generate(self.cfg, "morning", self.as_of, use_codex=True)
        folder = self.cfg.path("report_dir") / "morning-2026-10-26"
        self.assertTrue((folder / "report.md").is_file())
        self.assertTrue((folder / "evidence.json").is_file())
        self.assertFalse((folder / "agent-report.md").exists())

    def test_failed_cli_does_not_publish_partial_narrative(self):
        with patch("garmin_rest_agent.codex.shutil.which", return_value="codex.exe"), \
             patch("garmin_rest_agent.codex.invoke", return_value=1):
            with self.assertRaises(ValueError):
                narrate(self.cfg, self.evidence, self.folder)
        self.assertFalse((self.folder / "agent-report.md").exists())

    def test_timeout_is_not_retried(self):
        with patch("garmin_rest_agent.codex.shutil.which", return_value="codex.exe"), \
             patch("garmin_rest_agent.codex.invoke",
                   side_effect=subprocess.TimeoutExpired("codex", 180)) as run:
            with self.assertRaisesRegex(ValueError, "超时"):
                narrate(self.cfg, self.evidence, self.folder)
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
