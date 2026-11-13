"""Native-backend metadata. Returned bindings still contain private account metadata.

OCI's optional SDK is loaded lazily. No IAM or upload methods are exposed.
Exact-version deletion is for the separately approved cleanup caller only.
SDK model/transport references: https://docs.oracle.com/en-us/iaas/tools/python/latest/api/object_storage/client/oci.object_storage.ObjectStorageClient.html
The installed SDK version is recorded, not a hash of all its dependencies.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib
import re
from pathlib import Path

import image_gate as files


class InspectionError(files.ImageGateError):
    pass


def require(condition, message="Backend inspection returned incomplete or unexpected metadata."):
    if not condition:
        raise InspectionError(message)


def sdk():
    try:
        return importlib.import_module("oci")
    except ImportError:
        raise InspectionError("OCI Python SDK unavailable; use an environment with the OCI Python SDK installed.") from None


def text(value, maximum=1024):
    require(isinstance(value, str) and 0 < len(value) <= maximum and all(ord(c) >= 32 and ord(c) != 127 for c in value))
    return value


def identity(config_file: Path, profile: str):
    """Return private SDK config in memory and a binding without key/passphrase values."""
    oci = sdk()
    try:
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", profile) is not None)
        path = config_file.expanduser().absolute()
        raw = files.read_private(path)
        config = oci.config.from_file(file_location=str(path), profile_name=profile)
        oci.config.validate_config(config)
        require(not config.get("log_requests") and config.get("auth", "APIKey") in {"APIKey", "api_key"})
        require(not any(k in config for k in ("key_content", "security_token_file", "delegation_token_file", "authentication_type")))
        key_path = Path(config["key_file"]).expanduser()
        require(key_path.is_absolute(), "The configured signing key path must be absolute.")
        key = files.read_private(key_path)
        private_key = oci.signer.load_private_key(key, config.get("pass_phrase"))
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
        require(isinstance(private_key, RSAPrivateKey) and private_key.key_size >= 2048)
        public = private_key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        fingerprint = ":".join(f"{b:02x}" for b in hashlib.md5(public, usedforsecurity=False).digest())
        require(config["fingerprint"].lower() == fingerprint, "Configured fingerprint does not match the signing key.")
        require(files.read_private(path) == raw and files.read_private(key_path) == key, "Identity files changed during inspection.")
        effective = {k: config[k] for k in ("tenancy", "user", "region")}
        for kind, field in (("tenancy", "tenancy"), ("user", "user")):
            require(re.fullmatch(r"ocid1\." + kind + r"\.oc1\.[A-Za-z0-9.-]{1,250}", text(effective[field])) is not None)
        effective.update(fingerprint=fingerprint, key_file=str(key_path), key_content=key.decode(),
                         pass_phrase=config.get("pass_phrase"), log_requests=False)
        binding = {k: effective[k] for k in ("tenancy", "user", "region", "fingerprint")}
        binding.update(config_file=str(path), config_sha256=files.sha(raw), profile=profile,
                       key_file=str(key_path), key_sha256=files.sha(key), public_key_fingerprint=fingerprint,
                       sdk_version=text(oci.__version__, 80))
        return effective, binding
    except InspectionError:
        raise
    except Exception:
        raise InspectionError("Unable to validate the private API-key configuration and signing key.") from None


class Inspector:
    def __init__(self, config, target):
        self.oci = sdk()
        require(set(target) == {"bucket", "namespace", "region", "bucket_id", "compartment_id", "tenancy_id"})
        self.target = dict(target)
        for field, pattern in (("region", r"[a-z]+-[a-z]+-\d+"), ("namespace", r"[A-Za-z0-9_-]{1,64}"),
                               ("bucket", r"[A-Za-z0-9_.-]{1,256}")):
            require(re.fullmatch(pattern, text(target[field])) is not None)
        for field, kind in (("bucket_id", "bucket"), ("compartment_id", "compartment"), ("tenancy_id", "tenancy")):
            require(re.fullmatch(r"ocid1\." + kind + r"\.oc1\.[A-Za-z0-9.-]{1,250}", text(target[field])) is not None)
        require(config.get("tenancy") == target["tenancy_id"], "Signing identity does not match the approved tenancy.")
        try:
            self.retry = self.oci.retry.NoneRetryStrategy()
            effective = dict(config, region=target["region"], log_requests=False)
            signer = self.oci.signer.Signer(tenancy=config["tenancy"], user=config["user"],
                fingerprint=config["fingerprint"], private_key_file_location=None,
                private_key_content=config["key_content"], pass_phrase=config.get("pass_phrase"))
            self.client = self.oci.object_storage.ObjectStorageClient(effective, signer=signer,
                service_endpoint=f"https://objectstorage.{target['region']}.oraclecloud.com",
                retry_strategy=self.retry, timeout=(5, 20))
            self.client.base_client.session.trust_env = False
            self.client.base_client.session.proxies = {}
        except Exception:
            raise InspectionError("Unable to initialize the read-only OCI metadata client.") from None

    def _call(self, method, *args, missing=False, **kwargs):
        try:
            return getattr(self.client, method)(*args, retry_strategy=self.retry, **kwargs)
        except Exception as error:
            if missing and getattr(error, "status", None) == 404 and getattr(error, "code", None) == "ObjectNotFound":
                return None
            raise InspectionError("OCI metadata read failed; absence or authorization could not be established.") from None

    def _headers(self, response):
        require(getattr(response, "status", None) == 200)
        require(hasattr(getattr(response, "headers", None), "items") and len(response.headers) <= 64)
        headers = {}
        for key, value in response.headers.items():
            key = text(key, 256).lower()
            require(key not in headers)
            headers[key] = text(value, 8192)
        require("content-range" not in headers)
        return headers

    def _args(self):
        return self.target["namespace"], self.target["bucket"]

    def preflight(self):
        namespace = self._call("get_namespace")
        self._headers(namespace)
        require(namespace.data == self.target["namespace"], "Caller namespace does not match the approved target.")
        bucket = self._call("get_bucket", *self._args())
        self._headers(bucket)
        value = bucket.data
        require(all(getattr(value, key, None) == self.target[field] for key, field in
                    (("name", "bucket"), ("namespace", "namespace"), ("id", "bucket_id"), ("compartment_id", "compartment_id"))))
        require(getattr(value, "public_access_type", None) == "NoPublicAccess" and getattr(value, "versioning", None) == "Enabled",
                "Backend bucket must remain private and versioning-enabled.")
        return dict(self.target, public_access_type="NoPublicAccess", versioning="Enabled")

    @staticmethod
    def _name(name):
        require(re.fullmatch(r"[A-Za-z0-9_./-]{1,512}", text(name)) is not None
                and all(p not in {"", ".", ".."} for p in name.split("/")))
        return name

    def _metadata(self, response, version_id=None):
        headers = self._headers(response)
        require(headers.get("content-encoding", "identity").lower() == "identity")
        require(re.fullmatch(r"[0-9]{1,20}", headers.get("content-length", "")) is not None)
        found = text(headers.get("version-id"))
        require(version_id is None or version_id == found)
        return dict(version_id=found, etag=text(headers.get("etag")), size=int(headers["content-length"]))

    def head(self, name):
        response = self._call("head_object", *self._args(), self._name(name), missing=True)
        return None if response is None else self._metadata(response)

    def delete_version(self, name, version_id, etag=None):
        """Caller must approve the exact target/name/version manifest independently."""
        kwargs = {"version_id": text(version_id)}
        if etag is not None:
            kwargs["if_match"] = text(etag)
        response = self._call("delete_object", *self._args(), self._name(name), **kwargs)
        require(getattr(response, "status", None) == 204, "Exact-version deletion returned an unexpected result.")

    def object(self, name, version_id=None, limit=65536):
        require(type(limit) is int and 1 <= limit <= 65536)
        kwargs = {} if version_id is None else {"version_id": text(version_id)}
        response = self._call("get_object", *self._args(), self._name(name), missing=True, **kwargs)
        if response is None:
            return None
        try:
            metadata = self._metadata(response, version_id)
            require(metadata["size"] <= limit, "Backend object exceeds the inspection limit.")
            raw = response.data.raw.read(limit + 1, decode_content=False)
            require(isinstance(raw, bytes) and len(raw) == metadata["size"] and len(raw) <= limit,
                    "Backend object size did not match its metadata.")
            return dict(metadata, bytes=raw)
        except InspectionError:
            raise
        except Exception:
            raise InspectionError("Unable to read the bounded backend object.") from None
        finally:
            try:
                response.data.close()
            except Exception:
                pass

    def inventory(self, prefix, names):
        require(isinstance(prefix, str) and prefix.endswith("/"))
        self._name(prefix[:-1])
        require(isinstance(names, (list, tuple)) and len(names) == 4 and all(isinstance(name, str) for name in names))
        require(len(set(names)) == 4)
        allowed = {self._name(name) for name in names}
        require(all(name.startswith(prefix) for name in allowed))
        result = {"objects": [], "versions": []}
        pages = 0
        for kind in result:
            cursor, cursors, seen = None, set(), set()
            while True:
                pages += 1
                require(pages <= 16, "Backend inventory pagination exceeded the limit.")
                kwargs = dict(prefix=prefix, limit=128, fields="name,size,etag,timeModified")
                if cursor:
                    kwargs["start" if kind == "objects" else "page"] = cursor
                response = self._call("list_objects" if kind == "objects" else "list_object_versions", *self._args(), **kwargs)
                headers = self._headers(response)
                require(getattr(response.data, "prefixes", None) in (None, []))
                rows = getattr(response.data, "objects" if kind == "objects" else "items", None)
                require(isinstance(rows, list) and len(rows) + len(result[kind]) <= (4 if kind == "objects" else 128))
                for row in rows:
                    require(isinstance(getattr(row, "name", None), str) and row.name in allowed)
                    marker = getattr(row, "is_delete_marker", None) if kind == "versions" else False
                    require(type(marker) is bool)
                    size, etag = getattr(row, "size", None), getattr(row, "etag", None)
                    require((marker and size is None) or (type(size) is int and 0 <= size <= 65536))
                    if not marker or etag is not None:
                        text(etag)
                    item = dict(name=row.name, size=size, etag=etag)
                    identity_key = row.name
                    if kind == "versions":
                        version_id = text(getattr(row, "version_id", None))
                        stamp = getattr(row, "time_modified", None)
                        require(isinstance(stamp, dt.datetime) and stamp.tzinfo is not None)
                        item.update(version_id=version_id, is_delete_marker=marker,
                                    time_modified=stamp.astimezone(dt.timezone.utc).isoformat())
                        identity_key = (row.name, version_id)
                    require(identity_key not in seen)
                    seen.add(identity_key); result[kind].append(item)
                if kind == "objects":
                    require("opc-next-page" not in headers)
                    cursor = getattr(response.data, "next_start_with", None)
                else:
                    require(getattr(response.data, "next_start_with", None) is None)
                    cursor = headers.get("opc-next-page")
                if cursor is None:
                    break
                text(cursor, 4096)
                require(cursor not in cursors and bool(rows), "Backend inventory pagination is incomplete.")
                cursors.add(cursor)
        for item in result["objects"]:
            found = self.head(item["name"])
            require(found is not None and all(found[k] == item[k] for k in ("size", "etag")))
            require(any(v["name"] == item["name"] and v["version_id"] == found["version_id"]
                        and not v["is_delete_marker"] and v["size"] == item["size"] and v["etag"] == item["etag"]
                        for v in result["versions"]), "Current backend object changed during inventory.")
            item["version_id"] = found["version_id"]
        return {key: sorted(rows, key=lambda r: (r["name"], r["version_id"])) for key, rows in result.items()}
