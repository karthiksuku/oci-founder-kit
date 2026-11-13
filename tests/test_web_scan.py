"""Behavior and safety checks for read-only hosted-web migration discovery."""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("web_scan", ROOT / "skills/oci-migrate-web/scripts/web_scan.py")
web_scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(web_scan)


class WebScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "app"
        self.root.mkdir()

    def put(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def codes(self, report):
        return {f["code"] for f in report["findings"]}

    def test_next_vercel_features_and_names_without_values(self):
        self.put("package.json", json.dumps({"dependencies": {"next": "16", "@vercel/blob": "1", "@vercel/kv": "1"}}))
        self.put("vercel.json", json.dumps({"crons": [{"path": "CANARY_PATH"}], "redirects": [], "env": {"PRIVATE_VALUE": "CANARY_CONFIG"}}))
        self.put("app/api/tasks/route.ts", "const x = process.env.DATABASE_URL; const y = process.env['BLOB_TOKEN']; const a = 'CANARY_INLINE';")
        self.put("middleware.ts", "export const runtime = 'edge';")
        self.put("app/page.tsx", "import Image from 'next/image'; revalidateTag('CANARY_TAG');")
        report = web_scan.scan(self.root)
        self.assertEqual(report["frameworks"], ["Next.js"])
        self.assertTrue({"next-runtime", "blob-storage", "kv-store", "scheduled-jobs", "routing", "server-routes", "middleware", "edge-runtime", "image-optimization", "cache-revalidation"} <= self.codes(report))
        self.assertEqual(report["environment_variable_names"], ["BLOB_TOKEN", "DATABASE_URL"])
        output = json.dumps(report) + web_scan.markdown(report)
        for canary in ("CANARY_INLINE", "CANARY_CONFIG", "CANARY_PATH", "CANARY_TAG", "PRIVATE_VALUE"):
            self.assertNotIn(canary, output)

    def test_netlify_and_monorepo_dependencies(self):
        self.put("apps/site/package.json", json.dumps({"devDependencies": {"astro": "fixture", "@netlify/functions": "fixture"}}))
        self.put("apps/site/netlify.toml", "[functions]\ndirectory = 'DO_NOT_EMIT'\n[[edge_functions]]\nfunction = 'DO_NOT_EMIT'\n[[redirects]]\nfrom = '/DO_NOT_EMIT'\n")
        report = web_scan.scan(self.root)
        self.assertEqual(report["frameworks"], ["Astro"])
        self.assertTrue({"hosting-config", "platform-functions", "edge-runtime", "routing"} <= self.codes(report))
        self.assertNotIn("DO_NOT_EMIT", json.dumps(report))

    def test_skips_sensitive_hidden_generated_and_symlink_files(self):
        self.put(".env", "process.env.DO_NOT_READ_ENV")
        self.put("credentials.ts", "process.env.DO_NOT_READ_CREDENTIALS")
        self.put(".vercel/project.json", "process.env.DO_NOT_READ_HIDDEN")
        self.put("node_modules/pkg/index.js", "process.env.DO_NOT_READ_DEPENDENCY")
        self.put("dist/bundle.js", "process.env.DO_NOT_READ_BUILD")
        outside = Path(self.tmp.name) / "outside.ts"
        outside.write_text("process.env.DO_NOT_READ_SYMLINK")
        (self.root / "linked.ts").symlink_to(outside)
        (self.root / "linked-dir").symlink_to(outside.parent, target_is_directory=True)
        report = web_scan.scan(self.root)
        self.assertEqual(report["environment_variable_names"], [])
        self.assertEqual(report["coverage"]["files_read"], 0)

    def test_rejects_symlink_scan_root(self):
        link = Path(self.tmp.name) / "app-link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            web_scan.scan(link)

    def test_never_executes_configuration(self):
        marker = self.root / "executed.txt"
        self.put("next.config.mjs", "import fs from 'node:fs'; fs.writeFileSync('executed.txt', 'bad'); export default {};")
        before = (self.root / "next.config.mjs").read_bytes()
        report = web_scan.scan(self.root)
        self.assertEqual(report["coverage"]["files_read"], 1)
        self.assertFalse(marker.exists())
        self.assertEqual((self.root / "next.config.mjs").read_bytes(), before)

    def test_malformed_input_reports_limits_not_source_excerpts(self):
        self.put("vercel.json", "{CANARY_BROKEN_INPUT")
        self.put("package.json", "[]")
        self.put("netlify.toml", "[broken CANARY_TOML")
        report = web_scan.scan(self.root)
        self.assertEqual(report["coverage"]["status"], "incomplete")
        self.assertEqual(len(report["coverage"]["warnings"]), 3)
        self.assertNotIn("CANARY", json.dumps(report))

    def test_file_and_byte_limits_are_visible(self):
        self.put("one.ts", "process.env.ONE")
        self.put("two.ts", "process.env.TWO")
        self.assertEqual(web_scan.scan(self.root, max_files=1)["coverage"]["status"], "incomplete")
        self.assertEqual(web_scan.scan(self.root, max_bytes=1)["coverage"]["status"], "incomplete")

    def test_large_nonregular_and_invalid_utf8_inputs(self):
        self.put("large.ts", "x" * (web_scan.MAX_FILE_BYTES + 1))
        (self.root / "binary.ts").write_bytes(b"\xff")
        os.mkfifo(self.root / "pipe.ts")
        report = web_scan.scan(self.root)
        self.assertEqual(report["coverage"]["status"], "incomplete")
        self.assertEqual(report["coverage"]["files_read"], 0)

    def test_unsupported_filenames_cannot_inject_report_markup(self):
        self.put("evil`code`.ts", "export const runtime = 'edge';")
        output = web_scan.markdown(web_scan.scan(self.root))
        self.assertNotIn("evil`code`", output)
        self.assertIn("path omitted", output)

    def test_no_findings_does_not_claim_portability(self):
        report = web_scan.scan(self.root)
        self.assertIn("does not establish portability", web_scan.markdown(report))
        self.assertEqual(report["coverage"]["status"], "bounded-static-scan")

    def test_output_refuses_source_overwrite_and_symlink(self):
        source = self.put("index.ts", "process.env.APP_REGION")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(web_scan.main([str(self.root), "--out", str(source)]), 2)
        self.assertEqual(source.read_text(), "process.env.APP_REGION")
        out_link = Path(self.tmp.name) / "report-link.md"
        target = Path(self.tmp.name) / "not-created.md"
        out_link.symlink_to(target)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(web_scan.main([str(self.root), "--out", str(out_link)]), 2)
        self.assertFalse(target.exists())

    def test_new_report_is_private_and_json_stdout_works(self):
        self.put("package.json", '{"dependencies":{"next":"fixture"}}')
        output = Path(self.tmp.name) / "scan.json"
        self.assertEqual(web_scan.main([str(self.root), "--format", "json", "--out", str(output)]), 0)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(output.read_text())["schema"], web_scan.SCHEMA)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(web_scan.main([str(self.root), "--format", "json"]), 0)
        self.assertEqual(json.loads(stdout.getvalue())["frameworks"], ["Next.js"])

    def test_fixture_remains_a_discovery_example(self):
        report = web_scan.scan(ROOT / "examples/migrate-vercel")
        self.assertTrue({"next-runtime", "blob-storage", "middleware", "server-routes", "routing", "scheduled-jobs"} <= self.codes(report))
        self.assertEqual(report["coverage"]["status"], "bounded-static-scan")


if __name__ == "__main__":
    unittest.main()
