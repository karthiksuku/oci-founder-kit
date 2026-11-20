"""Projection and read-only registry contract tests; no credentials or cloud access."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sre_scan as scan

NOW = 1760000000
DIGEST = "sha256:" + "f" * 64
CONFIG = "sha256:" + "3" * 64
REV = "a" * 40
STAMP = "2025-10-09T08:53:00Z"


def observed():
    version = {"Version": scan.VERSION}
    src = {"SchemaVersion": 2, "Trivy": version, "Results": [
        {"Class": "lang-pkgs", "Type": "npm", "Packages": [{"Name":"express", "Version":"1", "Relationship":"direct"}]},
        *[{"Class": "config", "Type": kind, "Misconfigurations": [{"Status": "PASS"}]}
          for kind in ("terraform", "dockerfile")]]}
    img = {"SchemaVersion": 2, "Trivy": version, "Metadata": {"OS": {"Family": "alpine", "Name": "3.22"}, "ImageID": CONFIG},
           "Results": [{"Class": "os-pkgs", "Packages": [{}]}, {"Class": "lang-pkgs", "Type": "node-pkg", "Packages": [{"Name":"express", "Version":"1", "FilePath":"app/node_modules/express/package.json"}]}]}
    dev = copy.deepcopy(src)
    dev["Results"][0]["Vulnerabilities"] = [{"Severity": "HIGH"}]
    return src, img, dev


def report(s=None, i=None, d=None, selected_lock=None):
    src, img, dev = observed()
    return scan.projection(s or src, i or img, d or dev, {"Version": scan.VERSION, "VulnerabilityDB": {"Version": 2, "UpdatedAt": STAMP}},
                           {"packages": [{"name": "fixture"}], "spdxVersion": "SPDX-2.3"}, source_revision=REV,
                           image_digest=DIGEST, config=CONFIG, sbom_digest=CONFIG, now=NOW, selected_lock=selected_lock)


class Scan(unittest.TestCase):
    def test_scoped_coverage_requires_selected_lock_and_its_shipped_next_version(self):
        source, image, dev = observed()
        lock = "apps/web/package-lock.json"
        scope = (lock, scan.lock_identity(lock, "0"*64))
        sibling = dict(source["Results"][0], Target="demo/package-lock.json",
                       Packages=[{"Name":"next","Version":"1","Relationship":"direct"}])
        source["Results"] += [sibling]
        selected = dict(sibling, Target=lock, Packages=[{"Name":"next","Version":"2","Relationship":"direct"}])
        source["Results"][0] = selected
        runtime = image["Results"][1]["Packages"][0]
        runtime.update(Name="next", Version="1", FilePath="srv/node_modules/next/package.json")
        def read():
            projection = report(source, image, dev, selected_lock=scope)
            return scan.gate_status(projection, now=NOW, image_digest=DIGEST, selected_lock_sha256=scope[1])
        self.assertEqual(read(), "unknown")  # Only a sibling's dependency shipped.
        runtime["Version"] = "2"
        self.assertEqual(read(), "passed")
        value = report(source, image, dev, selected_lock=scope)
        self.assertEqual(scan.gate_status(value, now=NOW, image_digest=DIGEST,
                        selected_lock_sha256=scan.lock_identity(sibling["Target"], "0"*64)), "unknown")
        self.assertEqual(scan.gate_status(report(), now=NOW, image_digest=DIGEST, selected_lock_sha256=scope[1]), "unknown")
        selected["Vulnerabilities"] = [{"Severity":"HIGH"}]
        self.assertEqual(read(), "blocked")
        selected["Vulnerabilities"] = []
        source["Results"].append(selected)
        self.assertEqual(read(), "unknown")
        selected["Target"] = "other/package-lock.json"
        self.assertEqual(read(), "unknown")

    def test_candidate_identity_and_database_freshness(self):
        clean = report()
        self.assertEqual(scan.gate_status(clean, image_digest=DIGEST, source_revision=REV, now=NOW), "passed")
        for altered in ({"image_digest": CONFIG}, {"scanner_sha256": "0" * 64},
                        {"source_revision": "b" * 40}, {"database_updated_at": NOW - 86401},
                        {"observed_at": NOW + 1}, {"database_schema": 1}):
            self.assertEqual(scan.gate_status(dict(clean, **altered), image_digest=DIGEST, source_revision=REV, now=NOW), "unknown")

    def test_dev_is_distinct_from_runtime_and_private_payload_is_not_projected(self):
        src, img, dev = observed()
        src["Results"][0].update(Vulnerabilities=[{"Severity": "HIGH"}])
        value = report(src, img, dev)
        self.assertEqual(scan.gate_status(value, image_digest=DIGEST, now=NOW), "blocked")
        img["Results"][1]["Vulnerabilities"] = [{"Severity": "HIGH"}]
        src["Results"][0]["Secrets"] = [{"Match": "synthetic-private-value"}]
        value = report(src, img, dev)
        self.assertEqual((value["counts"]["high"], value["counts"]["secrets"]), (2, 1))
        self.assertNotIn("synthetic-private-value", str(value))
        self.assertEqual(scan.gate_status(value, image_digest=DIGEST, now=NOW), "blocked")

    def test_base_tooling_or_wrong_version_is_not_application_coverage(self):
        src, img, dev = observed()
        for pkg in ({"Name":"express", "Version":"1", "FilePath":"usr/local/lib/node_modules/npm/node_modules/express/package.json"},
                    {"Name":"express", "Version":"2", "FilePath":"app/node_modules/express/package.json"},
                    {"Name":"npm", "Version":"1", "FilePath":"usr/local/lib/node_modules/npm/package.json"}):
            img["Results"][1]["Packages"] = [pkg]
            val = report(src, img, dev)
            self.assertEqual(scan.gate_status(val, image_digest=DIGEST, now=NOW), "unknown")
        src["Results"][0]["Vulnerabilities"] = [{"Severity":"CRITICAL"}]
        self.assertEqual(scan.gate_status(report(src,img,dev), image_digest=DIGEST, now=NOW), "blocked")

    def test_missing_coverage_never_passes(self):
        src, img, dev = observed()
        for removed in ("os_packages", "runtime_packages", "production_lock_packages", "terraform_checks", "dockerfile_checks"):
            value = report(src, img, dev)
            value["counts"][removed] = 0
            self.assertEqual(scan.gate_status(value, image_digest=DIGEST, now=NOW), "unknown")
        img["Metadata"]["ImageID"] = DIGEST
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_INVENTORY"):
            report(src, img, dev)

    def test_config_failure_and_unknown_severity(self):
        src, img, dev = observed()
        src["Results"][1]["Misconfigurations"] = [{"Status": "FAIL"}]
        self.assertEqual(scan.gate_status(report(src, img, dev), image_digest=DIGEST, now=NOW), "blocked")
        img["Results"][0]["Vulnerabilities"] = [{"Severity": "UNKNOWN"}]
        self.assertEqual(scan.gate_status(report(i=img), image_digest=DIGEST, now=NOW), "unknown")


class Registry(unittest.TestCase):
    def setUp(self):
        self.comp, self.repo = "test-compartment", "test-repository"
        self.image, self.scan = "ocid1.containerimage.oc1.test.synthetic", "ocid1.vsscontainerscanresult.oc1.test.synthetic"
        self.cfg = {"compartment_id": self.comp, "registry_id": self.repo, "image_digest": DIGEST}
        self.data = {
            "repository": {"id": self.repo, "compartment-id": self.comp, "is-public": False, "display-name": "test"},
            "image": {"id": self.image, "compartment-id": self.comp, "repository-id": self.repo, "repository-name": "test",
                      "digest": DIGEST, "time-created": "2025-10-08T00:00:00Z"},
            "result": {"id": self.scan, "compartment-id": self.comp, "target-compartment-id": self.comp, "repository": "test",
                       "image": DIGEST, "time-started": STAMP, "time-finished": STAMP, "highest-problem-severity": "NONE", "problem-count": 0},
        }

    def verdict(self, list_id=None, denied=False, page=False, second=None):
        def read(args):
            if denied:
                raise PermissionError
            if "list" in args:
                rows = [{"id": list_id or self.scan, "time-started": STAMP}]
                if second:
                    rows.append({"id":"another", "time-started":second})
                return {"data": {"items": rows}, "opc-next-page": "more" if page else None}
            return {"data": self.data[args[2] if args[0] == "artifacts" else "result"]}
        summary = scan.registry_result(read, self.cfg, image_id=self.image, scan_id=self.scan, now=NOW)
        self.assertNotIn(self.comp, str(summary))
        return scan.registry_status(summary, image_digest=DIGEST, now=NOW)

    def test_latest_exact_digest_required(self):
        self.assertEqual(self.verdict(), "passed")
        self.assertEqual(self.verdict(page=True, second="2025-10-08T00:01:00Z"), "passed")
        self.assertEqual(self.verdict(page=True), "unknown")
        self.assertEqual(self.verdict(page=True, second=STAMP), "unknown")
        self.assertEqual(self.verdict(list_id="different"), "unknown")
        self.assertEqual(self.verdict(denied=True), "unknown")
        self.data["result"]["image"] = "mutable"
        self.assertEqual(self.verdict(), "unknown")

    def test_reject_wrong_scope_and_high(self):
        self.data["result"].update({"highest-problem-severity": "HIGH", "problem-count": 1})
        self.assertEqual(self.verdict(), "blocked")
        self.data["repository"]["is-public"] = True
        self.assertEqual(self.verdict(), "unknown")
