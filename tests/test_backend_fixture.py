"""Fixed synthetic state and real loopback lifecycle; no Terraform/cloud calls."""

from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "oci-deploy" / "scripts"))
import backend_fixture as fixture  # noqa: E402

RUN = "synthetic-20261113"
LINEAGE = "123e4567-e89b-12d3-a456-426614174000"


class SyntheticStateTests(unittest.TestCase):
    def state(self):
        return fixture.synthetic(RUN, 1, LINEAGE, 4)

    def test_canonical_schema_and_explicit_metadata(self):
        raw = self.state()
        value = fixture.validate(raw, RUN, 1)
        self.assertEqual(raw, json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
        self.assertEqual(set(value), fixture.STATE_KEYS)
        self.assertEqual(value["lineage"], LINEAGE)
        self.assertEqual(value["serial"], 4)
        self.assertEqual(set(value["outputs"]), {"kit_run", "generation"})

    def test_generated_lineage_and_default_serial(self):
        value = fixture.validate(fixture.synthetic(RUN, 1), RUN, 1)
        self.assertEqual(value["serial"], 0)
        self.assertEqual(len(value["lineage"]), 36)

    def test_v2_preserves_verified_lineage_and_changes_only_generation_serial(self):
        original = fixture.validate(self.state(), RUN, 1)
        updated = fixture.validate(fixture.v2(self.state(), RUN), RUN, 2)
        expected = json.loads(self.state())
        expected["serial"] += 1
        expected["outputs"]["generation"]["value"] = 2
        self.assertEqual(updated, expected)
        self.assertEqual(updated["lineage"], original["lineage"])

    def test_v2_rejects_wrong_run_generation_and_overflow(self):
        for raw, run in ((self.state(), "different"), (fixture.synthetic(RUN, 2), RUN),
                         (fixture.synthetic(RUN, 1, LINEAGE, fixture.MAX_SERIAL), RUN)):
            with self.subTest(run=run), self.assertRaises(fixture.FixtureError):
                fixture.v2(raw, run)

    def test_constructor_arguments_are_strict(self):
        for run in ("", "../escape", "secret\nvalue", "a" * 65, 123):
            with self.subTest(run=run), self.assertRaises(fixture.FixtureError):
                fixture.synthetic(run, 1)
        for generation in (True, 1.0, 0, 3, "1"):
            with self.subTest(generation=generation), self.assertRaises(fixture.FixtureError):
                fixture.synthetic(RUN, generation)
        for serial in (True, 1.0, -1, fixture.MAX_SERIAL + 1):
            with self.subTest(serial=serial), self.assertRaises(fixture.FixtureError):
                fixture.synthetic(RUN, 1, serial=serial)
        for lineage in ("not-a-uuid", LINEAGE.upper(), LINEAGE.replace("-", ""), 1):
            with self.subTest(lineage=lineage), self.assertRaises(fixture.FixtureError):
                fixture.synthetic(RUN, 1, lineage)

    def test_unknown_fields_resources_and_output_changes_refused(self):
        mutations = [lambda v: v.update(extra="do-not-print"),
                     lambda v: v.update(version=True), lambda v: v.update(terraform_version="1.0.0"),
                     lambda v: v.update(resources=[{"type": "real_resource"}]),
                     lambda v: v.update(check_results=[]), lambda v: v.update(lineage="invalid"),
                     lambda v: v.update(serial=True), lambda v: v["outputs"].update(extra={}),
                     lambda v: v["outputs"]["generation"].update(value=True),
                     lambda v: v["outputs"]["generation"].update(type="string"),
                     lambda v: v["outputs"]["kit_run"].update(sensitive=False),
                     lambda v: v["outputs"].pop("kit_run")]
        for mutate in mutations:
            value = json.loads(self.state());mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(fixture.FixtureError) as error:
                fixture.validate(json.dumps(value).encode(), RUN, 1)
            self.assertNotIn("do-not-print", str(error.exception))

    def test_duplicate_noninteger_malformed_and_oversize_json_refused(self):
        for raw in (b'{"version":4,"version":4}', self.state().replace(b'"serial":4', b'"serial":4.0'),
                    self.state().replace(b'"serial":4', b'"serial":NaN'), b'[]', b'\xff',
                    b' ' * (fixture.MAX_BYTES + 1), b'{"secret":"do-not-print"',
                    self.state().replace(b'"type":"number"', b'"type":"number","type":"number"')):
            with self.subTest(raw_length=len(raw)), self.assertRaises(fixture.FixtureError) as error:
                fixture.validate(raw, RUN, 1)
            self.assertNotIn("do-not-print", str(error.exception))

    def test_fixed_module_has_no_backend_resources_or_external_provider(self):
        for kind in ("holder", "contender"):
            value = json.loads(fixture.module(kind))
            self.assertEqual(set(value), {"terraform", "variable", "data", "output"})
            self.assertEqual(value["terraform"], {"required_version": "= 1.16.6"})
            source = value["data"]["terraform_remote_state"]["fixture"]
            self.assertEqual(source, {"backend": "http", "config": {
                "address": "http://127.0.0.1:${var.fixture_port}/" + kind, "retry_max": 0}})
            condition = value["variable"]["fixture_port"]["validation"][0]["condition"]
            self.assertIn("floor(var.fixture_port) == var.fixture_port", condition)
            self.assertIn("65535", condition)
        for kind in ("../holder", "holder?x=1", "http://example.com", None):
            with self.subTest(kind=kind), self.assertRaises(fixture.FixtureError):
                fixture.module(kind)


class LoopbackTests(unittest.TestCase):
    def request(self, port, path, method="GET"):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_only_first_holder_blocks_and_contender_can_proceed(self):
        raw = fixture.synthetic(RUN, 1)
        with fixture.LoopbackFixture(raw) as server, ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.request, server.port, "/holder")
            try:
                self.assertTrue(server.holder_seen.wait(1))
                self.assertFalse(first.done())
                self.assertEqual(self.request(server.port, "/contender"), (200, raw))
                self.assertEqual(self.request(server.port, "/holder"), (200, raw))
            finally:
                server.release()
            self.assertEqual(first.result(timeout=2), (200, raw))
        self.assertEqual(server.counts(), {"/holder": 2, "/contender": 1, "rejected": 0, "holder_timeouts": 0})
        self.assertFalse(server._thread.is_alive())

    def test_context_exit_releases_holder_even_on_error(self):
        server = fixture.LoopbackFixture(fixture.synthetic(RUN, 1))
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                with server:
                    first = pool.submit(self.request, server.port, "/holder")
                    self.assertTrue(server.holder_seen.wait(1))
                    raise RuntimeError("synthetic failure")
            self.assertEqual(first.result(timeout=2)[0], 200)
        self.assertFalse(server._thread.is_alive())

    def test_holder_deadline_is_bounded_and_failure_is_explicit(self):
        with mock.patch.object(fixture, "HOLDER_WAIT_SECONDS", 0.05):
            with fixture.LoopbackFixture(fixture.synthetic(RUN, 1)) as server:
                self.assertEqual(self.request(server.port, "/holder")[0], 504)
                self.assertEqual(server.counts()["holder_timeouts"], 1)

    def test_paths_queries_methods_and_reuse_refused(self):
        server = fixture.LoopbackFixture(fixture.synthetic(RUN, 1))
        with server:
            for path, method in (("/holder?x=1", "GET"), ("/%68older", "GET"),
                                 ("/other", "GET"), ("/contender", "POST"), ("/holder", "HEAD")):
                self.assertEqual(self.request(server.port, path, method)[0], 405)
            self.assertEqual(server.counts()["rejected"], 5)
        with self.assertRaises(fixture.FixtureError):
            server.__enter__()

    def test_invalid_response_refused_before_binding(self):
        for raw in (b"{}", b'{"outputs":[]}', b"secret"):
            with self.assertRaises(fixture.FixtureError):
                fixture.LoopbackFixture(raw)

    def test_thread_start_failure_closes_listening_socket(self):
        server = fixture.LoopbackFixture(fixture.synthetic(RUN, 1))
        with mock.patch("threading.Thread.start", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                server.__enter__()
        self.assertIsNone(server._server)


if __name__ == "__main__":
    unittest.main()
