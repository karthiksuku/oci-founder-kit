#!/usr/bin/env python3
"""Deterministic SPDX inventory of the actual release archive, without installing code.

Files are complete for the manifest archive. Dependency declarations are not
installed packages: Python transitives, OS libraries and runtime images need a
separate image scan. No application checkout or private configuration is scanned.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(content, archive_name, archive_digest, version):
    package_id = "SPDXRef-Archive"
    files, packages, relationships = [], [], []
    declarations = []
    for name, data in sorted(content.items()):
        file_id = "SPDXRef-File-" + sha(name.encode())
        files.append({"SPDXID": file_id, "fileName": "./" + name,
                      "checksums": [{"algorithm": "SHA256", "checksumValue": sha(data)}],
                      "licenseConcluded": "NOASSERTION", "copyrightText": "NOASSERTION"})
        relationships.append({"spdxElementId": package_id, "relationshipType": "CONTAINS", "relatedSpdxElement": file_id})
        path = PurePosixPath(name)
        if path.name == "package-lock.json":
            lock = json.loads(data)
            for location, entry in sorted(lock.get("packages", {}).items()):
                if not location or not isinstance(entry, dict) or not entry.get("version"):
                    continue
                package_name = entry.get("name") or location.rsplit("node_modules/", 1)[-1]
                declarations.append((name, package_name, str(entry["version"]), "npm lock declaration; package not bundled", file_id))
        elif path.name.startswith("requirements") and path.suffix == ".txt":
            for line in data.decode().splitlines():
                match = re.fullmatch(r"\s*([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([A-Za-z0-9_.+!-]+)\s*(?:#.*)?", line)
                if match:
                    declarations.append((name, match[1], match[2], "Python direct pin; transitive dependencies unresolved", file_id))
        elif path.name == ".terraform.lock.hcl":
            for provider, provider_version in re.findall(r'provider\s+"([^"]+)"\s*\{\s*version\s*=\s*"([^"]+)"', data.decode()):
                declarations.append((name, provider, provider_version, "Terraform provider lock; provider binary not bundled", file_id))
    for source, name, declared_version, scope, source_id in sorted(declarations):
        identity = "SPDXRef-Declared-" + sha((source + "\0" + name + "\0" + declared_version).encode())
        # Multiple nested npm locations may describe the same package version.
        if any(package["SPDXID"] == identity for package in packages):
            continue
        packages.append({"SPDXID": identity, "name": name, "versionInfo": declared_version,
                         "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
                         "licenseConcluded": "NOASSERTION", "licenseDeclared": "NOASSERTION",
                         "copyrightText": "NOASSERTION", "comment": scope + "; declared in " + source})
        relationships.append({"spdxElementId": source_id, "relationshipType": "OTHER", "relatedSpdxElement": identity,
                              "comment": "Declares a dependency; does not establish installed runtime composition."})
    packages.insert(0, {"SPDXID": package_id, "name": archive_name, "versionInfo": version,
                       "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
                       "checksums": [{"algorithm": "SHA256", "checksumValue": archive_digest}],
                       "licenseConcluded": "NOASSERTION", "licenseDeclared": "NOASSERTION",
                       "copyrightText": "NOASSERTION",
                       "comment": "Complete SHA-256 file inventory; SPDX package verification code is not computed."})
    return {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
            "name": archive_name, "documentNamespace": "https://github.com/karthiksuku/oci-founder-kit/sbom/" + archive_digest,
            "creationInfo": {"created": "1970-01-01T00:00:00Z", "creators": ["Tool: oci-kit-release-sbom-1"],
                             "comment": "Fixed timestamp for deterministic source inventory; not a build date."},
            "documentDescribes": [package_id], "packages": packages, "files": files, "relationships": relationships,
            "comment": "Exact archive files and selected dependency declarations only. Does not resolve Python transitives, "
                       "unlocked dependencies, Docker base layers, OS packages or deployed workloads. Reference images require "
                       "separate Syft scans. Founder application inventories stay private. Not a vulnerability assessment."}
