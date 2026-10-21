#!/usr/bin/env python3
"""Refresh the Terraform resource type lists the service map is tested against.

Writes tests/fixtures/provider-types/<provider>.json for:
  - oracle/oci: from `terraform providers schema -json` (authoritative), or the
    Terraform Registry when Terraform is not installed;
  - hashicorp/aws, hashicorp/azurerm, hashicorp/google: from the Terraform
    Registry's documentation index for the latest version.

Usage: python3 scripts/refresh_provider_types.py [--providers oci,aws,azurerm,google]
Network access is required. Nothing outside tests/fixtures is changed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "provider-types"
REGISTRY = "https://registry.terraform.io/v1/providers/{source}"
PROVIDERS = {"oci": ("oracle/oci", "oci_"), "aws": ("hashicorp/aws", "aws_"),
             "azurerm": ("hashicorp/azurerm", "azurerm_"), "google": ("hashicorp/google", "google_")}


def from_registry(source: str, prefix: str) -> tuple[str, list[str], str]:
    request = urllib.request.Request(REGISTRY.format(source=source), headers={"User-Agent": "oci-founder-kit"})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - fixed https host
        data = json.loads(response.read().decode("utf-8"))
    titles = [doc["title"] for doc in data.get("docs", [])
              if doc.get("category") == "resources" and doc.get("language", "hcl") == "hcl"]
    # Some providers title pages with the full type name, others without the prefix.
    names = {title if title.startswith(prefix) else prefix + title for title in titles}
    return data["version"], sorted(names), "Terraform Registry documentation index"


def from_schema(source: str) -> tuple[str, list[str], str]:
    with tempfile.TemporaryDirectory(prefix="tf-schema-") as tmp:
        Path(tmp, "main.tf").write_text(
            'terraform {\n  required_providers {\n    oci = { source = "%s" }\n  }\n}\n' % source)
        subprocess.run(["terraform", "init", "-input=false", "-no-color"], cwd=tmp, check=True,
                       capture_output=True, timeout=600)
        schema = subprocess.run(["terraform", "providers", "schema", "-json"], cwd=tmp, check=True,
                                capture_output=True, timeout=600).stdout
        lock = Path(tmp, ".terraform.lock.hcl").read_text()
    data = json.loads(schema)
    key = next(k for k in data["provider_schemas"] if k.endswith(source))
    version = next(line.split('"')[1] for line in lock.splitlines() if line.strip().startswith("version"))
    return version, sorted(data["provider_schemas"][key]["resource_schemas"]), "terraform providers schema -json"


CFN_SPEC = "https://d1uauaxba7bl26.cloudfront.net/latest/gzip/CloudFormationResourceSpecification.json"


def from_cloudformation_spec() -> tuple[str, list[str], str]:
    request = urllib.request.Request(CFN_SPEC, headers={"User-Agent": "oci-founder-kit", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - fixed https host
        raw = response.read()
    data = json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    return data["ResourceSpecificationVersion"], sorted(data["ResourceTypes"]), "AWS CloudFormation resource specification"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--providers", default=",".join(list(PROVIDERS) + ["cloudformation"]))
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    for name in args.providers.split(","):
        if name == "cloudformation":
            version, types, method = from_cloudformation_spec()
            record = {"_note": f"CloudFormation resource types, specification v{version}. SAM types "
                               "(AWS::Serverless::*) come from the SAM transform and are not listed.",
                      "provider": "aws-cloudformation", "version": version,
                      "captured_at": dt.date.today().isoformat(), "resource_types": types}
            (OUT / "cloudformation.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
            sys.stdout.write(f"cloudformation: v{version}, {len(types)} resource types\n")
            continue
        source, prefix = PROVIDERS[name]
        if name == "oci" and shutil.which("terraform"):
            version, types, method = from_schema(source)
        else:
            version, types, method = from_registry(source, prefix)
        record = {"_note": f"Resource types for {source} v{version} via {method}. Refresh with "
                           "scripts/refresh_provider_types.py.",
                  "provider": f"registry.terraform.io/{source}", "version": version,
                  "captured_at": dt.date.today().isoformat(), "resource_types": types}
        (OUT / f"{name}.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        sys.stdout.write(f"{name}: {source} v{version}, {len(types)} resource types\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
