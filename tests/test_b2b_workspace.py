"""Opt-in B2B acceptance against disposable PostgreSQL and Taskboard auth middleware."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceAcceptance(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("FOUNDER_KIT_SAAS_POSTGRES") == "1",
                         "Set FOUNDER_KIT_SAAS_POSTGRES=1 for two-organization PostgreSQL acceptance")
    def test_two_organizations(self):
        tools = sorted(Path("/usr/lib/postgresql").glob("*/bin/initdb"))
        self.assertTrue(tools, "Install PostgreSQL tools first")
        cmd = [sys.executable, str(ROOT / "blueprints/b2b-workspace/test_local.py"),
               "--postgres-bin", str(tools[-1].parent)]
        if os.environ.get("FOUNDER_KIT_MIGRATION_BROWSER") == "1":
            cmd.append("--browser")
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
