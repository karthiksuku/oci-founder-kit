"""Fixed synthetic state and loopback read fixture for an approved backend test.

This helper never runs Terraform or contacts OCI. The caller owns operation
approval, native process lifetime and private evidence. A local fixture does not
establish remote locking, IAM isolation, retained versions or recovery.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
import uuid

MAX_BYTES = 64 * 1024
MAX_SERIAL = 2 ** 63 - 1
HOLDER_WAIT_SECONDS = 30
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
STATE_KEYS = {"version", "terraform_version", "serial", "lineage", "outputs", "resources", "check_results"}


class FixtureError(ValueError):
    """A synthetic fixture input or lifecycle is invalid; no input is echoed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _arguments(run_id: str, generation: int) -> None:
    _require(isinstance(run_id, str) and RUN_ID.fullmatch(run_id) is not None, "Invalid synthetic run ID.")
    _require(type(generation) is int and generation in (1, 2), "Synthetic generation must be 1 or 2.")


def _lineage(value: object) -> str:
    _require(isinstance(value, str), "Synthetic lineage must be a canonical UUID.")
    try:
        valid = str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        valid = False
    _require(valid, "Synthetic lineage must be a canonical UUID.")
    return value


def _parse(raw: bytes) -> dict:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "Synthetic state must be bytes within 64 KiB.")

    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "Duplicate synthetic state fields are refused.")
            result[key] = value
        return result

    def invalid_number(_value):
        raise FixtureError("Synthetic state numbers must be exact integers.")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_float=invalid_number, parse_constant=invalid_number)
    except (ValueError, UnicodeError, RecursionError):
        raise FixtureError("Malformed synthetic state.") from None
    _require(isinstance(value, dict), "Synthetic state must be an object.")
    return value


def synthetic(run_id: str, generation: int, lineage: str | None = None, serial: int = 0) -> bytes:
    """Build only the fixed v4 state; no caller-provided resources or metadata."""
    _arguments(run_id, generation)
    _require(type(serial) is int and 0 <= serial <= MAX_SERIAL, "Synthetic serial is out of bounds.")
    lineage = _lineage(str(uuid.uuid4()) if lineage is None else lineage)
    return _canonical({"version": 4, "terraform_version": "1.16.6", "serial": serial, "lineage": lineage,
                       "outputs": {"kit_run": {"value": run_id, "type": "string"},
                                   "generation": {"value": generation, "type": "number"}},
                       "resources": [], "check_results": None})


def validate(raw: bytes, run_id: str, generation: int) -> dict:
    """Reject any content outside the exact synthetic-state contract."""
    _arguments(run_id, generation)
    value = _parse(raw)
    _require(set(value) == STATE_KEYS, "Missing or unexpected synthetic state fields.")
    _require(type(value["version"]) is int and value["version"] == 4
             and value["terraform_version"] == "1.16.6", "Unexpected synthetic state version.")
    _require(type(value["serial"]) is int and 0 <= value["serial"] <= MAX_SERIAL,
             "Synthetic serial is out of bounds.")
    _lineage(value["lineage"])
    expected = {"kit_run": {"value": run_id, "type": "string"},
                "generation": {"value": generation, "type": "number"}}
    outputs = value["outputs"]
    _require(isinstance(outputs, dict) and outputs == expected
             and type(outputs.get("generation", {}).get("value")) is int,
             "Unexpected synthetic outputs.")
    _require(value["resources"] == [] and value["check_results"] is None,
             "Synthetic state must contain no resources or check results.")
    return value


def v2(raw: bytes, run_id: str) -> bytes:
    """Derive the one allowed update from verified persisted generation 1."""
    previous = validate(raw, run_id, 1)
    _require(previous["serial"] < MAX_SERIAL, "Synthetic serial cannot be incremented safely.")
    return synthetic(run_id, 2, previous["lineage"], previous["serial"] + 1)


def module(path_kind: str) -> bytes:
    """Canonical main.tf.json; caller supplies backend separately, never here."""
    _require(path_kind in ("holder", "contender"), "Unknown fixture path.")
    return _canonical({
        "terraform": {"required_version": "= 1.16.6"},
        "variable": {"fixture_port": {"type": "number", "nullable": False,
                     "validation": [{"condition": "${var.fixture_port >= 1 && var.fixture_port <= 65535 && floor(var.fixture_port) == var.fixture_port}",
                                     "error_message": "fixture_port must be an integer from 1 through 65535."}]}},
        "data": {"terraform_remote_state": {"fixture": {"backend": "http", "config": {
            "address": "http://127.0.0.1:${var.fixture_port}/" + path_kind, "retry_max": 0}}}},
        "output": {"kit_run": {"value": "${data.terraform_remote_state.fixture.outputs.kit_run}"},
                   "generation": {"value": "${data.terraform_remote_state.fixture.outputs.generation}"}},
    })


class _Server(ThreadingHTTPServer):
    # Join handlers on close; bounded socket reads prevent abandoned clients
    # from leaving cleanup blocked after the holder event has been released.
    daemon_threads = False
    block_on_close = True

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(2)
        return connection, address

    def handle_error(self, request, client_address):
        pass  # Never echo request headers or data in host logs.


class LoopbackFixture:
    """Serve fixed synthetic bytes; only the first /holder GET waits for release."""

    def __init__(self, response: bytes):
        value = _parse(response)
        try:
            validate(response, value["outputs"]["kit_run"]["value"], value["outputs"]["generation"]["value"])
        except (KeyError, TypeError):
            raise FixtureError("Invalid loopback synthetic state.") from None
        self._response = response
        self.holder_seen = threading.Event()
        self._release = threading.Event()
        self._guard = threading.Lock()
        self._counts = {"/holder": 0, "/contender": 0, "rejected": 0, "holder_timeouts": 0}
        self._server = None
        self._thread = None
        self._used = False

    @property
    def port(self) -> int:
        _require(self._server is not None, "Loopback fixture is not active.")
        return self._server.server_port

    def release(self) -> None:
        self._release.set()

    def counts(self) -> dict[str, int]:
        with self._guard:
            return dict(self._counts)

    def __enter__(self):
        _require(not self._used, "Loopback fixtures cannot be reused.")
        self._used = True
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def reply(self, status, body=b""):
                self.close_connection = True
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                except OSError:
                    pass

            def reject(self):
                with fixture._guard:
                    fixture._counts["rejected"] += 1
                self.reply(405)

            do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_TRACE = do_CONNECT = reject

            def do_GET(self):
                if self.path not in ("/holder", "/contender"):
                    self.reject()
                    return
                kind = self.path
                with fixture._guard:
                    fixture._counts[kind] += 1
                    first_holder = kind == "/holder" and fixture._counts[kind] == 1
                if first_holder:
                    fixture.holder_seen.set()
                    if not fixture._release.wait(HOLDER_WAIT_SECONDS):
                        with fixture._guard:
                            fixture._counts["holder_timeouts"] += 1
                        self.reply(504)
                        return
                self.reply(200, fixture._response)

        self._server = _Server(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={"poll_interval": 0.05}, name="backend-fixture")
        try:
            self._thread.start()
        except BaseException:
            self._server.server_close()
            self._server = None
            raise
        return self

    def __exit__(self, *_exc):
        self.release()
        try:
            self._server.shutdown()
        finally:
            self._server.server_close()
            self._thread.join(timeout=3)
            self._server = None
        _require(not self._thread.is_alive(), "Loopback fixture did not stop normally.")
