"""Inspect Terraform backend inputs without invoking Terraform or a cloud API.

This is a conservative declaration scanner, not an HCL evaluator. The caller
must authorize remote initialization separately and recheck the returned hashes
before execution. Backend cache configuration can contain credentials; keep the
returned metadata private. Errors deliberately omit source and metadata values.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path

MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 8_000_000
MAX_FILES = 512
MAX_TOKENS = 200_000
MAX_DEPTH = 128
BACKEND_TYPE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


class BackendConfigError(Exception):
    """Backend configuration cannot be safely inspected."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BackendConfigError(message)


def _open_directory(path: Path) -> int:
    _require(".." not in path.parts, "Parent-relative stack paths are refused.")
    absolute = path.absolute()
    fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _fingerprint(info: os.stat_result) -> tuple:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _read_at(directory: int, name: str) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                 "Terraform inputs must be regular files with one link.")
        _require(before.st_size <= MAX_FILE_BYTES, "Terraform input exceeds the size limit.")
        raw = stream.read(MAX_FILE_BYTES + 1)
        after = os.fstat(stream.fileno())
    named = os.stat(name, dir_fd=directory, follow_symlinks=False)
    _require(len(raw) <= MAX_FILE_BYTES and len(raw) == after.st_size,
             "Terraform input exceeds the size limit or changed during inspection.")
    _require(_fingerprint(before) == _fingerprint(after) == _fingerprint(named),
             "Terraform input changed during inspection.")
    return raw


def _json(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "Duplicate JSON fields are refused.")
            result[key] = value
        return result

    def constant(_value):
        raise BackendConfigError("Non-finite JSON values are refused.")

    def number(value):
        parsed = float(value)
        _require(math.isfinite(parsed), "Non-finite JSON values are refused.")
        return parsed

    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs,
                           parse_constant=constant, parse_float=number)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BackendConfigError("Terraform JSON is malformed or too deeply nested.") from exc
    _require(isinstance(value, dict), "Terraform JSON must contain an object.")
    return value


class _HCL:
    """Tokenize enough HCL to find only root terraform block declarations."""

    def __init__(self, raw: bytes):
        try:
            self.text = raw.decode("utf-8-sig")
        except UnicodeError as exc:
            raise BackendConfigError("Terraform source must be UTF-8.") from exc
        _require(not any(ord(c) < 32 and c not in "\t\n\r" for c in self.text),
                 "Control characters in Terraform source are refused.")
        self.position = 0

    def _space(self) -> bool:
        text, pos = self.text, self.position
        if text[pos].isspace():
            self.position += 1
        elif text[pos] == "#" or text.startswith("//", pos):
            end = text.find("\n", pos)
            self.position = len(text) if end < 0 else end + 1
        elif text.startswith("/*", pos):
            end = text.find("*/", pos + 2)
            _require(end >= 0, "Unterminated HCL comment.")
            self.position = end + 2
        else:
            return False
        return True

    def _heredoc(self) -> None:
        start = re.match(r"<<(-?)([A-Za-z_][A-Za-z0-9_-]*)[ \t]*\r?\n", self.text[self.position:])
        _require(start is not None, "Unsupported or malformed HCL heredoc.")
        self.position += start.end()
        while self.position < len(self.text):
            end = self.text.find("\n", self.position)
            end = len(self.text) if end < 0 else end
            line = self.text[self.position:end].rstrip("\r")
            if start[1]:
                line = line.lstrip(" \t")
            self.position = min(end + 1, len(self.text))
            if line == start[2]:
                return
        raise BackendConfigError("Unterminated HCL heredoc.")

    def _template(self, depth: int) -> None:
        _require(depth <= MAX_DEPTH, "HCL nesting exceeds the limit.")
        braces = 1
        while self.position < len(self.text):
            if self._space():
                continue
            char = self.text[self.position]
            if char == '"':
                self._quoted(depth + 1)
            elif self.text.startswith("<<", self.position):
                self._heredoc()
            else:
                self.position += 1
                braces += (char == "{") - (char == "}")
                _require(braces <= MAX_DEPTH, "HCL nesting exceeds the limit.")
                if not braces:
                    return
        raise BackendConfigError("Unterminated HCL template expression.")

    def _quoted(self, depth: int = 0) -> tuple[str, str]:
        _require(depth <= MAX_DEPTH, "HCL nesting exceeds the limit.")
        self.position += 1
        value, template = [], False
        escapes = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
        while self.position < len(self.text):
            char = self.text[self.position]
            if char == '"':
                self.position += 1
                return ("template" if template else "string", "".join(value))
            _require(char not in "\n\r", "Unterminated HCL quoted string.")
            if self.text.startswith(("$${", "%%{"), self.position):
                value.append(self.text[self.position + 1:self.position + 3])
                self.position += 3
            elif self.text.startswith(("${", "%{"), self.position):
                template = True
                self.position += 2
                self._template(depth + 1)
            elif char == "\\":
                self.position += 1
                _require(self.position < len(self.text), "Unterminated HCL escape.")
                char = self.text[self.position]
                if char in ("u", "U"):
                    count = 4 if char == "u" else 8
                    digits = self.text[self.position + 1:self.position + count + 1]
                    _require(len(digits) == count and re.fullmatch(r"[0-9A-Fa-f]+", digits) is not None,
                             "Invalid HCL Unicode escape.")
                    number = int(digits, 16)
                    _require(number <= 0x10FFFF and not 0xD800 <= number <= 0xDFFF,
                             "Invalid HCL Unicode escape.")
                    value.append(chr(number))
                    self.position += count + 1
                else:
                    _require(char in escapes, "Unsupported HCL escape.")
                    value.append(escapes[char])
                    self.position += 1
            else:
                value.append(char)
                self.position += 1
        raise BackendConfigError("Unterminated HCL quoted string.")

    def tokens(self) -> list[tuple[str, str]]:
        tokens, brackets = [], []
        while self.position < len(self.text):
            if self._space():
                continue
            char = self.text[self.position]
            if char == '"':
                token = self._quoted()
            elif self.text.startswith("<<", self.position):
                self._heredoc()
                token = ("heredoc", "")
            elif char.isalpha() or char == "_":
                start = self.position
                while self.position < len(self.text):
                    current = self.text[self.position]
                    if not (current.isalnum() or current in "_-"):
                        break
                    self.position += 1
                token = ("identifier", self.text[start:self.position])
            else:
                self.position += 1
                token = ("symbol", char)
                if char in "{[(":
                    brackets.append(char)
                    _require(len(brackets) <= MAX_DEPTH, "HCL nesting exceeds the limit.")
                elif char in "}])":
                    _require(bool(brackets) and brackets.pop() == {"}": "{", "]": "[", ")": "("}[char],
                             "Unbalanced HCL delimiters.")
            tokens.append(token)
            _require(len(tokens) <= MAX_TOKENS, "HCL token count exceeds the limit.")
        _require(not brackets, "Unbalanced HCL delimiters.")
        return tokens


def _hcl_declarations(raw: bytes) -> tuple[list[str], bool]:
    tokens = _HCL(raw).tokens()
    types, cloud = [], False
    depth, terraform_depth = 0, None
    for index, token in enumerate(tokens):
        kind, value = token
        if depth == 0 and token == ("identifier", "terraform"):
            _require(tokens[index + 1:index + 2] == [("symbol", "{")],
                     "Malformed terraform block header.")
            terraform_depth = 1
        elif terraform_depth is not None and depth == terraform_depth and value == "state_store":
            raise BackendConfigError("Provider-defined state stores are not supported by this gate.")
        elif terraform_depth is not None and depth == terraform_depth and value in ("backend", "cloud"):
            _require(kind == "identifier", "Malformed backend or cloud declaration.")
            if value == "cloud":
                _require(tokens[index + 1:index + 2] == [("symbol", "{")], "Malformed cloud block.")
                cloud = True
            else:
                header = tokens[index + 1:index + 3]
                _require(len(header) == 2 and header[0][0] in ("identifier", "string")
                         and BACKEND_TYPE.fullmatch(header[0][1]) is not None
                         and header[1] == ("symbol", "{"), "Malformed backend block.")
                types.append(header[0][1])
        if token == ("symbol", "{"):
            depth += 1
        elif token == ("symbol", "}"):
            depth -= 1
            if depth == 0:
                terraform_depth = None
    return types, cloud


def _blocks(value: object) -> list[dict]:
    blocks = value if isinstance(value, list) else [value]
    _require(bool(blocks) and all(isinstance(block, dict) for block in blocks),
             "Malformed Terraform JSON block.")
    return blocks


def _json_declarations(value: dict) -> tuple[list[str], bool]:
    types, cloud = [], False
    if "terraform" not in value:
        return types, cloud
    for block in _blocks(value["terraform"]):
        _require("state_store" not in block, "Provider-defined state stores are not supported by this gate.")
        if "cloud" in block:
            _blocks(block["cloud"])
            cloud = True
        if "backend" in block:
            backends = block["backend"]
            _require(isinstance(backends, dict) and bool(backends), "Malformed JSON backend block.")
            for kind, body in backends.items():
                _require(BACKEND_TYPE.fullmatch(kind) is not None, "Invalid backend type.")
                types.extend([kind] * len(_blocks(body)))
    return types, cloud


def _metadata(raw: bytes) -> dict | None:
    value = _json(raw)
    _require(type(value.get("version")) is int and value["version"] == 3,
             "Unsupported Terraform backend metadata version.")
    allowed = {"version", "terraform_version", "backend", "state_store", "remote", "serial", "lineage"}
    _require(not set(value) - allowed, "Unknown or noncanonical backend metadata fields are refused.")
    _require(value.get("state_store") is None and value.get("remote") is None,
             "Provider-defined or legacy remote state metadata is not supported.")
    backend = value.get("backend")
    if backend is not None:
        _require(isinstance(backend, dict) and not set(backend) - {"type", "config", "hash"}
                 and isinstance(backend.get("type"), str)
                 and BACKEND_TYPE.fullmatch(backend["type"]) is not None
                 and isinstance(backend.get("config"), dict), "Malformed Terraform backend metadata.")
        if "hash" in backend:
            _require(type(backend["hash"]) is int and 0 <= backend["hash"] < 2 ** 64,
                     "Malformed Terraform backend metadata hash.")
    return backend


def _sources(directory: int) -> list[str]:
    names = sorted(name for name in os.listdir(directory)
                   if name.endswith((".tf", ".tf.json", ".auto.tfvars", ".auto.tfvars.json"))
                   or name in (".terraform.lock.hcl", "terraform.tfvars", "terraform.tfvars.json"))
    _require(len(names) <= MAX_FILES, "Terraform source count exceeds the limit.")
    _require(all(not any(ord(char) < 32 or ord(char) == 127 for char in name) for name in names),
             "Control characters in Terraform filenames are refused.")
    return names


def inspect_backend(stack: Path) -> dict:
    """Return private backend metadata and input hashes; never execute commands."""
    _require(os.environ.get("TF_WORKSPACE", "") in ("", "default"),
             "Only the default Terraform workspace is supported.")
    _require(os.environ.get("TF_DATA_DIR", "") in ("", ".terraform", str(stack.absolute() / ".terraform")),
             "Redirected Terraform data directories are refused.")
    result = {"types": [], "declarations": [], "cloud": False, "metadata": None,
              "metadata_sha256": None, "source_sha256": {}, "workspace": "default"}
    try:
        directory = _open_directory(stack)
        try:
            names, total = _sources(directory), 0
            for name in names:
                raw = _read_at(directory, name)
                total += len(raw)
                _require(total <= MAX_TOTAL_BYTES, "Terraform inputs exceed the total size limit.")
                result["source_sha256"][name] = hashlib.sha256(raw).hexdigest()
                parsed = _json(raw) if name.endswith(".json") else None
                if name.endswith((".tf", ".tf.json")):
                    types, cloud = _json_declarations(parsed) if parsed is not None else _hcl_declarations(raw)
                    result["declarations"].extend({"file": name, "type": kind} for kind in types)
                    result["cloud"] |= cloud
            _require(names == _sources(directory), "Terraform sources changed during inspection.")
            result["types"] = sorted({entry["type"] for entry in result["declarations"]})
            if ".terraform" in os.listdir(directory):
                cache = os.open(".terraform", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                try:
                    cache_names = os.listdir(cache)
                    if "environment" in cache_names:
                        _require(_read_at(cache, "environment").strip() == b"default",
                                 "Only the default Terraform workspace is supported.")
                    if "terraform.tfstate" in cache_names:
                        raw = _read_at(cache, "terraform.tfstate")
                        metadata = _metadata(raw)
                        result["metadata"] = metadata
                        result["metadata_sha256"] = hashlib.sha256(raw).hexdigest()
                    _require(cache_names == os.listdir(cache), "Terraform cache changed during inspection.")
                finally:
                    os.close(cache)
        finally:
            os.close(directory)
    except (OSError, ValueError, RecursionError) as exc:
        raise BackendConfigError("Terraform inputs are unreadable, unsafe, or malformed.") from exc
    return result
