"""Opt-in actual Chromium acceptance against owned synthetic loopback fixtures."""
import json
import os
from pathlib import Path
import subprocess
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("FOUNDER_KIT_MIGRATION_BROWSER") == "1",
                     "Opt-in built Next.js, Taskboard dependencies and installed Chromium.")
class MigrationBrowser(unittest.TestCase):
    def test_actual_browser_workflows_negative_controls_and_source_preservation(self):
        result = subprocess.run(["node", str(ROOT / "scripts/browser_migration.mjs")], cwd=ROOT,
                                capture_output=True, text=True, timeout=200)
        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(len(report["checks"]), 5)
        self.assertEqual(len(report["negative_controls"]), 2)
        self.assertTrue(all(item["detected"] for item in report["negative_controls"]))
        self.assertTrue(report["source_preserved"])
        self.assertFalse(report["hosted_sign_in_verified"])
        self.assertFalse(report["cloud_calls"])
        self.assertNotIn("__Host-taskboard=", result.stdout + result.stderr)
        self.assertNotIn("127.0.0.1:", result.stdout + result.stderr)

    def test_interrupted_browser_run_reports_unknown_and_stops_owned_children(self):
        process = subprocess.Popen(["node", str(ROOT / "scripts/browser_migration.mjs")], cwd=ROOT,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            time.sleep(2)
            self.assertIsNone(process.poll())
            process.terminate()
            stdout, stderr = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 2, stdout)
            report = json.loads(stdout)
            self.assertTrue(report["interrupted"])
            self.assertEqual(report["status"], "unknown")
            self.assertFalse(report["cloud_calls"])
            self.assertNotIn("__Host-taskboard=", stdout + stderr)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
