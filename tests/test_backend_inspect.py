"""Read-only backend inspection fails closed; no OCI requests or stored keys."""

import datetime as dt
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "oci-deploy" / "scripts"))
import backend_inspect as inspect_backend

TARGET = dict(bucket="synthetic-bucket", namespace="syntheticnamespace", region="us-ashburn-1",
              bucket_id="ocid1.bucket.oc1.iad.synthetic", compartment_id="ocid1.compartment.oc1..synthetic",
              tenancy_id="ocid1.tenancy.oc1..synthetic")
PREFIX = "backend-check/synthetic/"
NAMES = [PREFIX + name for name in ("primary.tfstate", "primary.tfstate.lock",
                                   "recovery.tfstate", "recovery.tfstate.lock")]
NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def reply(data=None, headers=None, status=200):
    return NS(data=data, headers=headers or {}, status=status)


def version(name=NAMES[0], version_id="v1", marker=False):
    return NS(name=name, version_id=version_id, is_delete_marker=marker, size=None if marker else 2,
              etag=None if marker else "etag1", time_modified=NOW)


def current(name=NAMES[0]):
    return NS(name=name, size=2, etag="etag1")


class ReadError(Exception):
    def __init__(self, status, code):
        super().__init__("PRIVATE_SENTINEL")
        self.status, self.code = status, code


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.client = mock.Mock()
        self.client.get_namespace.return_value = reply(TARGET["namespace"])
        self.client.get_bucket.return_value = reply(NS(
            name=TARGET["bucket"], namespace=TARGET["namespace"], id=TARGET["bucket_id"],
            compartment_id=TARGET["compartment_id"], public_access_type="NoPublicAccess",
            versioning="Enabled"))
        self.client.list_objects.return_value = reply(NS(objects=[], prefixes=[], next_start_with=None))
        self.client.list_object_versions.return_value = reply(NS(items=[], prefixes=[]))
        self.client.head_object.return_value = reply(headers={"etag": "etag1", "content-length": "2",
                                                             "version-id": "v1"})
        self.sdk = NS(__version__="synthetic", signer=NS(Signer=mock.Mock()),
                      retry=NS(NoneRetryStrategy=mock.Mock()),
                      object_storage=NS(ObjectStorageClient=mock.Mock(return_value=self.client)))
        patch = mock.patch.object(inspect_backend, "sdk", return_value=self.sdk)
        patch.start(); self.addCleanup(patch.stop)
        self.config = dict(tenancy=TARGET["tenancy_id"], user="ocid1.user.oc1..synthetic", fingerprint="synthetic",
                           key_file="unused", key_content="synthetic", region="us-phoenix-1")
        self.reader = inspect_backend.Inspector(self.config, TARGET)

    def assert_refused(self, callback):
        with self.assertRaises(inspect_backend.InspectionError) as caught:
            callback()
        self.assertNotIn("PRIVATE_SENTINEL", str(caught.exception))

    def test_explicit_endpoint_signer_retry_and_no_proxies(self):
        options = self.sdk.object_storage.ObjectStorageClient.call_args.kwargs
        self.assertEqual(options["service_endpoint"], "https://objectstorage.us-ashburn-1.oraclecloud.com")
        self.assertEqual(options["timeout"], (5, 20))
        self.assertFalse(self.client.base_client.session.trust_env)
        self.assertEqual(self.client.base_client.session.proxies, {})
        self.assertEqual(self.sdk.object_storage.ObjectStorageClient.call_args.args[0]["region"], TARGET["region"])
        self.sdk.signer.Signer.assert_called_once()

    def test_preflight_exact_target_and_access(self):
        self.reader.preflight()
        self.client.get_namespace.assert_called_once()
        for field in ("id", "compartment_id", "name", "namespace", "public_access_type", "versioning"):
            original = getattr(self.client.get_bucket.return_value.data, field)
            setattr(self.client.get_bucket.return_value.data, field, "mismatch")
            self.assert_refused(self.reader.preflight)
            setattr(self.client.get_bucket.return_value.data, field, original)

    def test_identity_or_region_mismatch_refused_before_client_creation(self):
        self.assert_refused(lambda: inspect_backend.Inspector({**self.config, "tenancy": "other"}, TARGET))
        self.assert_refused(lambda: inspect_backend.Inspector(self.config, {**TARGET, "region": "host/escape"}))
        self.assert_refused(lambda: inspect_backend.Inspector(self.config, {**TARGET, "bucket_id": "ocid1.bucket.oc4.x.y"}))

    def test_namespace_mismatch_and_sdk_errors_redacted(self):
        self.client.get_namespace.return_value.data = "other"
        self.assert_refused(self.reader.preflight)
        self.client.get_namespace.side_effect = ReadError(403, "NotAuthorizedOrNotFound")
        self.assert_refused(self.reader.preflight)

    def test_empty_inventory_does_not_head_absent_keys(self):
        self.assertEqual(self.reader.inventory(PREFIX, NAMES), {"objects": [], "versions": []})
        self.client.head_object.assert_not_called()

    def test_complete_inventory_includes_markers_and_bound_current_version(self):
        self.client.list_objects.return_value.data.objects = [current()]
        self.client.list_object_versions.return_value.data.items = [version(NAMES[1], "marker", True), version()]
        result = self.reader.inventory(PREFIX, NAMES)
        self.assertEqual(result["objects"], [dict(name=NAMES[0], size=2, etag="etag1", version_id="v1")])
        self.assertTrue(result["versions"][1]["is_delete_marker"])
        self.assertIsNone(result["versions"][1]["etag"])
        self.assertEqual(result["versions"][0]["time_modified"], "2026-01-01T00:00:00+00:00")

    def test_both_pagination_protocols_followed(self):
        self.client.list_objects.side_effect = [reply(NS(objects=[current()], prefixes=[], next_start_with=NAMES[1])),
                                                reply(NS(objects=[], prefixes=[], next_start_with=None))]
        self.client.list_object_versions.side_effect = [reply(NS(items=[version()], prefixes=[]), {"opc-next-page": "next"}),
                                                        reply(NS(items=[version(NAMES[1], "m", True)], prefixes=[]))]
        self.assertEqual(len(self.reader.inventory(PREFIX, NAMES)["versions"]), 2)
        self.assertEqual(self.client.list_objects.call_args_list[1].kwargs["start"], NAMES[1])
        self.assertEqual(self.client.list_object_versions.call_args_list[1].kwargs["page"], "next")

    def test_unexpected_neighbor_duplicate_and_prefix_summary_refused(self):
        for objects, prefixes in (([current(PREFIX + "neighbor")], []), ([current(), current()], []), ([], [PREFIX])):
            self.client.list_objects.return_value.data = NS(objects=objects, prefixes=prefixes, next_start_with=None)
            self.assert_refused(lambda: self.reader.inventory(PREFIX, NAMES))

    def test_malformed_versions_and_current_mismatch_refused(self):
        for changes in ({"is_delete_marker": "false"}, {"size": True}, {"etag": None},
                        {"version_id": ""}, {"time_modified": None}, {"name": PREFIX + "neighbor"}):
            row = version()
            for key, value in changes.items(): setattr(row, key, value)
            self.client.list_object_versions.return_value.data.items = [row]
            self.assert_refused(lambda: self.reader.inventory(PREFIX, NAMES))
        self.client.list_object_versions.return_value.data.items = [version(version_id="old")]
        self.client.list_objects.return_value.data.objects = [current()]
        self.assert_refused(lambda: self.reader.inventory(PREFIX, NAMES))

    def test_page_cycles_and_page_or_row_bounds_refused(self):
        self.client.list_object_versions.return_value = reply(NS(items=[version()], prefixes=[]), {"opc-next-page": "loop"})
        self.assert_refused(lambda: self.reader.inventory(PREFIX, NAMES))
        self.client.list_object_versions.side_effect = [reply(NS(items=[version(version_id=str(i))], prefixes=[]),
                                                               {"opc-next-page": str(i)}) for i in range(20)]
        self.assert_refused(lambda: self.reader.inventory(PREFIX, NAMES))
        self.client.list_object_versions.side_effect = None
        self.client.list_object_versions.return_value = reply(NS(items=[version(version_id=str(i)) for i in range(129)], prefixes=[]))
        self.assert_refused(lambda: self.reader.inventory(PREFIX, NAMES))

    def test_partial_status_and_unexpected_continuation_refused(self):
        self.client.list_objects.return_value.status = 206
        self.assert_refused(lambda: self.reader.inventory(PREFIX, NAMES))
        self.client.list_objects.return_value.status = 200
        self.client.list_objects.return_value.headers = {"opc-next-page": "unexpected"}
        self.assert_refused(lambda: self.reader.inventory(PREFIX, NAMES))

    def object_reply(self, raw=b"{}", **headers):
        class Stream(io.BytesIO):
            def read(self, count, decode_content=False):
                return super().read(count)
        stream = Stream(raw)
        self.client.get_object.return_value = reply(NS(raw=stream, close=stream.close),
            {"etag": "etag1", "version-id": "v1", "content-length": str(len(raw)), **headers})
        return stream

    def test_bounded_object_reads_and_closes(self):
        stream = self.object_reply()
        self.assertEqual(self.reader.object(NAMES[0], "v1"), dict(bytes=b"{}", version_id="v1", etag="etag1", size=2))
        self.assertTrue(stream.closed)
        self.assertEqual(self.client.get_object.call_args.kwargs["version_id"], "v1")

    def test_oversize_truncated_or_changed_version_refused_and_closed(self):
        for raw, headers in ((b"abc", {"content-length": "2"}), (b"x", {"content-length": "2"}),
                             (b"{}", {"version-id": "other"}), (b"{}", {"content-length": "65537"}),
                             (b"{}", {"content-encoding": "gzip"})):
            stream = self.object_reply(raw, **headers)
            self.assert_refused(lambda: self.reader.object(NAMES[0], "v1"))
            self.assertTrue(stream.closed)

    def test_only_explicit_missing_object_returns_none(self):
        for method in ("get_object", "head_object"):
            call = self.reader.object if method == "get_object" else self.reader.head
            getattr(self.client, method).side_effect = ReadError(404, "ObjectNotFound")
            self.assertIsNone(call(NAMES[0]))
            for status, code in ((404, "NotFound"), (404, "NotAuthorizedOrNotFound"), (403, "ObjectNotFound")):
                getattr(self.client, method).side_effect = ReadError(status, code)
                self.assert_refused(lambda: call(NAMES[0]))

    def test_exact_version_delete_has_no_retry_or_unversioned_fallback(self):
        self.client.delete_object.return_value = reply(status=204)
        self.reader.delete_version(NAMES[0], "version1", "etag1")
        args, kwargs = self.client.delete_object.call_args
        self.assertEqual(args, (TARGET["namespace"], TARGET["bucket"], NAMES[0]))
        self.assertEqual(kwargs, dict(version_id="version1", if_match="etag1", retry_strategy=self.reader.retry))
        self.client.delete_object.reset_mock()
        self.assert_refused(lambda: self.reader.delete_version(NAMES[0], ""))
        self.client.delete_object.assert_not_called()
        self.client.delete_object.side_effect = ReadError(404, "ObjectNotFound")
        self.assert_refused(lambda: self.reader.delete_version(NAMES[0], "version1"))
        self.assertEqual(self.client.delete_object.call_count, 1)

    def test_malformed_models_are_refusals(self):
        self.client.list_objects.return_value.data.objects = [NS(name=["unhashable"])]
        self.assert_refused(lambda: self.reader.inventory(PREFIX, NAMES))
        self.client.get_bucket.return_value.data = NS()
        self.assert_refused(self.reader.preflight)


class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import oci
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
        except ImportError:
            raise unittest.SkipTest("optional OCI SDK and cryptography unavailable")
        cls.oci = oci
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_key, cls.serialization = key, serialization
        cls.key = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption())
        public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        cls.fingerprint = ":".join(f"{b:02x}" for b in hashlib.md5(public, usedforsecurity=False).digest())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.key_path = self.path / "synthetic.pem"
        self.key_path.write_bytes(self.key); self.key_path.chmod(0o600)
        self.config_path = self.path / "config"
        self.body = (f"[DEFAULT]\nuser=ocid1.user.oc1..synthetic\ntenancy={TARGET['tenancy_id']}\n"
                     f"fingerprint={self.fingerprint}\nkey_file={self.key_path}\nregion=us-ashburn-1\n")
        self.write(self.body)

    def write(self, body):
        self.config_path.write_text(body); self.config_path.chmod(0o600)

    def test_real_sdk_identity_binding_has_no_key_or_passphrase(self):
        config, binding = inspect_backend.identity(self.config_path, "DEFAULT")
        self.assertEqual(binding["key_sha256"], hashlib.sha256(self.key).hexdigest())
        self.assertEqual(binding["public_key_fingerprint"], self.fingerprint)
        self.assertEqual(binding["config_sha256"], hashlib.sha256(self.body.encode()).hexdigest())
        self.assertEqual(binding["sdk_version"], self.oci.__version__)
        self.assertNotIn("PRIVATE KEY", json.dumps(binding))
        self.assertNotIn("pass_phrase", binding)
        self.assertEqual(config["tenancy"], TARGET["tenancy_id"])

    def test_unsafe_files_fingerprint_auth_and_logging_refused(self):
        for suffix in ("auth=security_token\n", "security_token_file=/unused\n", "log_requests=true\n"):
            self.write(self.body + suffix)
            with self.assertRaises(inspect_backend.InspectionError): inspect_backend.identity(self.config_path, "DEFAULT")
        self.write(self.body.replace(self.fingerprint, "00:" * 15 + "00"))
        with self.assertRaises(inspect_backend.InspectionError): inspect_backend.identity(self.config_path, "DEFAULT")
        self.write(self.body); self.key_path.chmod(0o644)
        with self.assertRaises(inspect_backend.InspectionError): inspect_backend.identity(self.config_path, "DEFAULT")
        self.key_path.chmod(0o600)
        link = self.path / "link"; link.symlink_to(self.config_path)
        with self.assertRaises(inspect_backend.InspectionError): inspect_backend.identity(link, "DEFAULT")

    def test_relative_key_parent_symlink_and_oversize_config_refused(self):
        self.write(self.body.replace(str(self.key_path), self.key_path.name))
        with mock.patch.object(self.oci.config, "invalid_key_file_path_checker"), self.assertRaisesRegex(
                inspect_backend.InspectionError, "absolute"):
            inspect_backend.identity(self.config_path, "DEFAULT")
        link = self.path / "linked-parent"; link.symlink_to(self.path, target_is_directory=True)
        self.write(self.body.replace(str(self.key_path), str(link / self.key_path.name)))
        with self.assertRaises(inspect_backend.InspectionError): inspect_backend.identity(self.config_path, "DEFAULT")
        self.write(self.body + "#" * 1_000_001)
        with self.assertRaises(inspect_backend.InspectionError): inspect_backend.identity(self.config_path, "DEFAULT")

    def test_encrypted_key_phrase_stays_only_in_private_memory(self):
        phrase = "synthetic-runtime-passphrase"
        encrypted = self.private_key.private_bytes(self.serialization.Encoding.PEM, self.serialization.PrivateFormat.PKCS8,
                                                   self.serialization.BestAvailableEncryption(phrase.encode()))
        self.key_path.write_bytes(encrypted)
        self.write(self.body + "pass_phrase=" + phrase + "\n")
        config, binding = inspect_backend.identity(self.config_path, "DEFAULT")
        self.assertEqual(config["pass_phrase"], phrase)
        self.assertNotIn(phrase, json.dumps(binding))
        self.assertNotIn("PRIVATE KEY", json.dumps(binding))

    def test_installed_sdk_constructs_pinned_client_without_requests(self):
        config, _ = inspect_backend.identity(self.config_path, "DEFAULT")
        with mock.patch("requests.sessions.Session.request", side_effect=AssertionError("network forbidden")):
            reader = inspect_backend.Inspector(config, TARGET)
            self.addCleanup(reader.client.base_client.session.close)
            self.assertFalse(reader.client.base_client.session.trust_env)
            self.assertEqual(reader.client.base_client.endpoint, "https://objectstorage.us-ashburn-1.oraclecloud.com")
            self.assertIsInstance(reader.retry, self.oci.retry.NoneRetryStrategy)
            v = self.oci.object_storage.models.ObjectVersionSummary(name=NAMES[1], version_id="marker",
                    is_delete_marker=True, time_modified=NOW)
            with mock.patch.object(reader.client, "list_objects", return_value=reply(
                    self.oci.object_storage.models.ListObjects(objects=[]))), mock.patch.object(
                    reader.client, "list_object_versions", return_value=reply(
                    self.oci.object_storage.models.ObjectVersionCollection(items=[v]))):
                self.assertTrue(reader.inventory(PREFIX, NAMES)["versions"][0]["is_delete_marker"])

    def test_missing_sdk_error_has_actionable_generic_message(self):
        with mock.patch.object(inspect_backend.importlib, "import_module", side_effect=ImportError("PRIVATE_SENTINEL")):
            with self.assertRaisesRegex(inspect_backend.InspectionError, "OCI Python SDK") as caught:
                inspect_backend.identity(self.config_path, "DEFAULT")
            self.assertNotIn("PRIVATE_SENTINEL", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
