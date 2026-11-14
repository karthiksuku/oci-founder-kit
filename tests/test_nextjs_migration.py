"""Opt-in real Next.js HTTP parity; the repository suite installs no npm packages."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/migrate-nextjs"


class NextJsMigration(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("FOUNDER_KIT_NEXTJS_PARITY") == "1",
                         "Optional runtime rehearsal: build examples/migrate-nextjs, then set FOUNDER_KIT_NEXTJS_PARITY=1")
    def test_normal_and_standalone_servers_preserve_http_contract(self):
        if not shutil.which("node") or not (EXAMPLE / "node_modules/next/package.json").is_file():
            self.skipTest("Next.js dependencies unavailable; run the example's documented npm ci/build first")
        if not (EXAMPLE / ".next/reference/BUILD_ID").is_file():
            self.skipTest("Next.js reference build unavailable; run npm run build in examples/migrate-nextjs")
        result = subprocess.run([sys.executable, str(EXAMPLE / "parity.py")], cwd=EXAMPLE,
                                capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["result"], "passed")
        self.assertEqual(report["runtimes"], ["next-start", "standalone"])
        self.assertEqual(report["cloud"], "not_tested")


if __name__ == "__main__":
    unittest.main()
