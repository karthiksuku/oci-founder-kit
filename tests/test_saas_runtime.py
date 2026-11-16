"""Opt-in synthetic PostgreSQL/loopback SaaS integration, never an external DB."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SaaSRuntime(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("FOUNDER_KIT_SAAS_POSTGRES") == "1",
                         "Set FOUNDER_KIT_SAAS_POSTGRES=1 for isolated PostgreSQL and loopback SaaS acceptance")
    def test_real_durable_runtime(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node 22+ required for requested SaaS integration")
        binaries = sorted(Path("/usr/lib/postgresql").glob("*/bin/initdb"))
        self.assertTrue(binaries, "Install local PostgreSQL binaries for this requested integration")
        pg = binaries[-1].parent
        self.assertTrue((ROOT / "blueprints/saas-essentials/app/node_modules/pg").is_dir(), "Install reviewed SaaS dependencies first")
        with tempfile.TemporaryDirectory(prefix="saas-pg-") as temporary:
            directory = Path(temporary)
            socket = directory / "socket"; socket.mkdir(mode=0o700)
            data = directory / "data"
            subprocess.run([str(pg / "initdb"), "-D", str(data), "-A", "trust", "--no-instructions"], check=True, capture_output=True, timeout=30)
            started = False
            try:
                subprocess.run([str(pg / "pg_ctl"), "-D", str(data), "-l", str(directory / "server.log"),
                                "-o", f"-k {socket} -h '' -p 55439", "-w", "start"], check=True, capture_output=True, timeout=30)
                started = True
                environment = dict(os.environ, SAAS_TEST_DATABASE_URL=f"postgresql:///postgres?host={socket}&port=55439")
                result = subprocess.run([node, "--test", "--test-reporter=tap", "blueprints/saas-essentials/app/test/reliability.test.js"],
                                        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout[-7000:] + result.stderr[-1000:])
                self.assertRegex(result.stdout, r"# skipped 0\b")
                count = re.search(r"# tests (\d+)\b", result.stdout)
                self.assertIsNotNone(count)
                self.assertGreaterEqual(int(count[1]), 15)
            finally:
                if started:
                    subprocess.run([str(pg / "pg_ctl"), "-D", str(data), "-m", "immediate", "-w", "stop"], check=True, capture_output=True, timeout=30)
