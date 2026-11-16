"""Offline profile/expiry binding for approved native OCI backend operations.

JWT decoding is a local consistency check, not signature verification or proof of
permissions. OCI verifies the token when an approved client makes its request.
Refreshing a token requires a fresh plan; this module never refreshes or retries.
"""
from __future__ import annotations

import base64
import configparser
import os
import re
import time
from pathlib import Path

import image_gate as files

MIN_REMAINING_SECONDS = 600
MAX_CREDENTIAL_BYTES = 65536
PROFILE_FIELDS = {"tenancy", "user", "fingerprint", "region", "key_file", "security_token_file"}
IDENTIFIER = r"ocid1\.%s\.[a-z0-9_-]+\.[a-z0-9_-]*\.[a-z0-9]+"
REAUTH = ("Refresh a still-valid session with oci session refresh --profile <profile> --auth security_token, "
          "or use oci session authenticate for an expired session; then prepare and approve a fresh plan.")


def _read(path):
    """Read a bounded, owner-only credential without following any symlinks."""
    with files.directory(path.parent) as directory:
        parent = os.fstat(directory)
        files.require(parent.st_uid == os.getuid() and not parent.st_mode & 0o077,
                      "Session credential directories must be owner-only (0700).")
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            files.regular(stream.fileno())
            before = os.fstat(stream.fileno())
            files.require(before.st_size <= MAX_CREDENTIAL_BYTES, "Session credential file exceeds the size limit.")
            raw = stream.read(MAX_CREDENTIAL_BYTES + 1)
            after = os.fstat(stream.fileno())
        named = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        def identity(info):
            return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
        files.require(identity(before) == identity(after) == identity(named)
                      and len(raw) == after.st_size <= MAX_CREDENTIAL_BYTES,
                      "Session credential changed during inspection; prepare a fresh plan.")
        return raw


def _path(value):
    files.require(isinstance(value, str) and value and not any(ord(c) < 32 for c in value),
                  "Invalid session credential path.")
    files.require(not value.startswith("~") or value.startswith("~/"), "Use an absolute or ~/ session credential path.")
    path = Path(value).expanduser()
    files.require(path.is_absolute() and ".." not in path.parts, "Use an absolute session credential path without traversal.")
    return path


def _jwt(raw):
    text = raw.decode("ascii").strip()
    parts = text.split(".")
    files.require(len(parts) == 3 and all(re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts),
                  "Malformed session token. " + REAUTH)
    def decode(part):
        return files.parse(base64.b64decode(part + "=" * (-len(part) % 4), altchars=b"-_", validate=True))
    header, claims = decode(parts[0]), decode(parts[1])
    files.require(isinstance(header, dict) and header.get("alg") == "RS256" and isinstance(claims, dict),
                  "Unsupported session token format. " + REAUTH)
    return claims


def _inspect(config, config_file=None, include_material=False):
    """Return only mode/profile, hashes and expiry; never credential values."""
    mode, profile_name = config["auth"], config["config_file_profile"]
    if mode == "APIKey":
        return {"auth": mode, "profile": profile_name}
    files.require(mode == "SecurityToken", "Unsupported backend authentication mode.")
    try:
        config_path = _path(str(config_file)) if config_file is not None else Path.home() / ".oci" / "config"
        parser = configparser.ConfigParser(interpolation=None, default_section="__NO_INHERITANCE__")
        parser.optionxform = str
        parser.read_string(_read(config_path).decode("utf-8"))
        files.require(not parser.defaults() and parser.has_section(profile_name), "An explicit session profile is required.")
        profile = dict(parser[profile_name])
        files.require(not set(profile) - PROFILE_FIELDS and
                      all(profile.get(name) for name in ("tenancy", "user", "region", "key_file", "security_token_file")),
                      "Use a self-contained session profile with tenancy, user, region, key_file and security_token_file; inline secrets and overrides are refused.")
        for name, kind in (("tenancy", "tenancy"), ("user", "user")):
            files.require(re.fullmatch(IDENTIFIER % kind, profile[name]) is not None, "Invalid session profile identity.")
        files.require(re.fullmatch(r"[a-z]+-[a-z]+-\d+", profile["region"]) is not None, "Invalid session profile region.")
        token_path, key_path = _path(profile["security_token_file"]), _path(profile["key_file"])
        raw_token, raw_key = _read(token_path), _read(key_path)
        files.require(raw_key.startswith(tuple(b"-----BEGIN " + kind + b"-----" for kind in (b"PRIVATE KEY", b"RSA PRIVATE KEY"))),
                      "A private session signing key is required; encrypted keys are not supported by this path.")
        claims = _jwt(raw_token)
        files.require(claims.get("sub") == profile["user"] and claims.get("tenant") == profile["tenancy"],
                      "Session identity does not match the selected profile. " + REAUTH)
        now, expiry = time.time(), claims.get("exp")
        files.require(type(expiry) is int and expiry - now > MIN_REMAINING_SECONDS,
                      "Session is expired or has less than ten minutes remaining. " + REAUTH)
        for name in ("iat", "nbf"):
            if name in claims:
                files.require(type(claims[name]) is int and claims[name] <= now + 30 and claims[name] < expiry,
                              "Session timing is invalid or not yet valid. " + REAUTH)
        context = {"auth": mode, "profile": profile_name, "expires_at_epoch": expiry,
                "profile_sha256": files.sha(files.canonical({"path": str(config_path), "settings": profile})),
                "identity_sha256": files.sha(files.canonical({"sub": claims["sub"], "tenant": claims["tenant"]})),
                "key_sha256": files.sha(raw_key), "token_sha256": files.sha(raw_token)}
        if include_material:
            return context, {**profile, "key_content": raw_key, "security_token": raw_token.decode("ascii").strip(),
                             "session_config_file": str(config_path), "session_binding": context}
        return context
    except files.ImageGateError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError, configparser.Error):
        raise files.ImageGateError("Cannot safely inspect the private session configuration. " + REAUTH) from None


def inspect(config, config_file=None):
    return _inspect(config, config_file)


def session_material(profile, config_file):
    """Private SDK caller only: return binding and credential material in memory."""
    return _inspect({"auth": "SecurityToken", "config_file_profile": profile}, config_file, include_material=True)


def validate(config, expected):
    files.require(isinstance(expected, dict) and inspect(config) == expected,
                  "Authentication context changed, including any refreshed token. " + REAUTH)


def session_readiness(profile, config_file=None):
    """Doctor interface: safe expiry metadata or ValueError; no remote requests.

    Explicit configuration paths are available for readiness only. Native backend
    execution deliberately uses the default OCI config location.
    """
    try:
        files.require(isinstance(profile, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", profile),
                      "Invalid session profile name.")
        observed = inspect({"auth": "SecurityToken", "config_file_profile": profile}, config_file=config_file)
        return {"auth": observed["auth"], "expires_at_epoch": observed["expires_at_epoch"],
                "minimum_remaining_seconds": MIN_REMAINING_SECONDS,
                "verification": "local-consistency-only"}
    except files.ImageGateError as exc:
        raise ValueError(str(exc)) from None


def deadline(requested, context):
    expiry = context.get("expires_at_epoch")
    return min(requested, expiry - MIN_REMAINING_SECONDS) if expiry is not None else requested
