#!/usr/bin/env python3
"""Bounded HTTPS checks for an explicitly selected hardened Taskboard.

Anonymous reads are the default. --exercise opts into synthetic application
writes using two existing test sessions in a private file outside a Git tree.
No login automation, OCI APIs, deployment, restart or restore is performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import re
import secrets
import socket
import ssl
import stat
import sys
import threading
import time
from urllib.parse import urlsplit

MAX_RESPONSE = 65536
MAX_REQUESTS = 48
COOKIE = re.compile(r'__Host-taskboard=[A-Za-z0-9%._~:+/-]{16,4096}')
CSRF = re.compile(r'[A-Za-z0-9_-]{32,128}')
ID = re.compile(r'[1-9][0-9]{0,14}')


class CheckError(ValueError):
    """Generic failures only; never include response bodies or authentication."""


class Response:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    def json(self):
        try:
            return json.loads(self.body, object_pairs_hook=unique_fields)
        except (ValueError, UnicodeError, RecursionError):
            raise CheckError('Response could not be checked.') from None


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CheckError('Duplicate fields are refused.')
        result[key] = value
    return result


def validate_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (not isinstance(value, str) or len(value) > 512 or not value.isascii()
                or any(c.isspace() for c in value) or any(c in value for c in '\\?#')
                or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment
                or parsed.hostname.endswith('.') or parsed.netloc.endswith(':')
                or not 1 <= (443 if parsed.port is None else parsed.port) <= 65535):
            raise ValueError
        if not re.fullmatch(r'[A-Za-z0-9.-]+', parsed.hostname):
            raise ValueError
        return 'https://' + parsed.netloc.lower()
    except (ValueError, TypeError, AttributeError):
        raise CheckError('Select an exact HTTPS origin without credentials, path, query or fragment.') from None


def inside_git(path: Path) -> bool:
    return any((p / '.git').exists() for p in path.parents)


def private_read(path: Path, limit=16384, *, outside_git=False) -> bytes:
    path = path.expanduser().absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise CheckError('Private input must not use symlinks.')
    if outside_git and inside_git(path):
        raise CheckError('Keep session configuration outside Git repositories.')
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                               | getattr(os, 'O_NONBLOCK', 0)), 'rb') as handle:
            info = os.fstat(handle.fileno())
            if (not stat.S_ISREG(info.st_mode) or os.name == 'nt'
                    or info.st_uid != os.getuid() or info.st_mode & 0o077):
                raise CheckError('Private input must be an owned regular file with mode 600 or 400.')
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise CheckError('Private input exceeded its size limit.')
        return data
    except OSError:
        raise CheckError('Private input could not be read.') from None


def load_sessions(path: Path, origin: str) -> dict:
    try:
        data = json.loads(private_read(path, outside_git=True), object_pairs_hook=unique_fields)
        if (set(data) != {'schema', 'origin', 'users'} or data['schema'] != 'oci-production-sessions/1'
                or data['origin'] != origin or not isinstance(data['users'], dict)
                or set(data['users']) != {'a', 'b'}):
            raise ValueError
        users = data['users']
        if any(not isinstance(value, str) or not COOKIE.fullmatch(value) for value in users.values()):
            raise ValueError
        if users['a'] == users['b']:
            raise ValueError
        return dict(users)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CheckError('Use two distinct test-session cookies bound to the exact target origin.') from None


class HTTPSClient:
    """No proxies, redirects, retries, cross-origin requests or TLS bypass."""
    def __init__(self, origin: str, ca_file: Path | None = None):
        target = urlsplit(origin)
        self.host, self.port = target.hostname, target.port or 443
        self.context = ssl.create_default_context()
        if ca_file is not None:
            self.context.load_verify_locations(cadata=private_read(ca_file, 65536).decode('ascii'))
        self.deadline = time.monotonic() + 90
        self.calls = 0
        self.addresses = None

    def connect(self, address, timeout, source_address=None):
        if address != (self.host, self.port) or source_address is not None:
            raise CheckError('Unexpected connection target.')
        if self.addresses is None:
            resolved = queue.Queue(maxsize=1)
            def lookup():
                try:
                    resolved.put(socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM))
                except OSError:
                    resolved.put([])
            # A stalled system resolver may finish later, but this worker can
            # only resolve the selected name. It never sends an HTTP request.
            threading.Thread(target=lookup, daemon=True).start()
            try:
                self.addresses = resolved.get(timeout=max(0.01, min(5, self.deadline - time.monotonic())))[:4]
            except queue.Empty:
                raise CheckError('Name resolution exceeded its deadline.') from None
        for family, kind, protocol, _, endpoint in self.addresses:
            if time.monotonic() >= self.deadline:
                break
            sock = socket.socket(family, kind, protocol)
            try:
                sock.settimeout(min(timeout, self.deadline - time.monotonic()))
                sock.connect(endpoint)
                return sock
            except (OSError, ValueError):
                sock.close()
        raise CheckError('Selected target is unavailable.')

    def request(self, method, path, headers=None, body=None):
        if (method not in {'GET', 'POST', 'PATCH', 'PUT', 'DELETE'}
                or not re.fullmatch(r'/[A-Za-z0-9/_-]*', path)
                or self.calls >= MAX_REQUESTS or time.monotonic() >= self.deadline
                or body is not None and len(body) > 16384):
            raise CheckError('Request bounds were reached.')
        self.calls += 1
        remaining = self.deadline - time.monotonic()
        conn = http.client.HTTPSConnection(self.host, self.port, timeout=min(5, remaining), context=self.context)
        conn._create_connection = self.connect
        timer = None
        try:
            conn.connect()
            if time.monotonic() >= self.deadline:
                raise CheckError('Request deadline reached.')
            sock = conn.sock
            def expire():
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            timer = threading.Timer(max(0.01, min(10, self.deadline - time.monotonic())), expire)
            timer.daemon = True; timer.start()
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            data = bytearray()
            while True:
                if time.monotonic() >= self.deadline:
                    raise CheckError('Request deadline reached.')
                chunk = response.read1(min(8192, MAX_RESPONSE + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_RESPONSE:
                    raise CheckError('Response exceeded its size limit.')
            return Response(response.status, response.getheaders(), bytes(data))
        except (OSError, http.client.HTTPException, ValueError):
            raise CheckError('HTTPS request unavailable or exceeded bounds.') from None
        finally:
            if timer is not None:
                timer.cancel()
            conn.close()


def run(origin: str, *, exercise=False, sessions=None, ca_file=None, client=None) -> dict:
    origin = validate_origin(origin)
    if exercise and (not isinstance(sessions, dict) or set(sessions) != {'a', 'b'}):
        raise CheckError('Exercise requires two private test sessions.')
    if exercise and (any(not isinstance(v, str) or not COOKIE.fullmatch(v) for v in sessions.values())
                     or sessions['a'] == sessions['b']):
        raise CheckError('Exercise requires two distinct valid test-session cookies.')
    if sessions is not None and not exercise:
        raise CheckError('Sessions are only used with explicit exercise scope.')
    client = client or HTTPSClient(origin, ca_file)
    run_id = secrets.token_hex(12)
    result = {'schema': 'oci-production-check/1', 'scope': 'synthetic-application-exercise' if exercise else 'anonymous-read-checks',
              'status': 'unknown', 'run_id': run_id,
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'target_origin_sha256': hashlib.sha256(origin.encode()).hexdigest(),
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'production_readiness_established': False, 'checks': [],
              'cleanup': {'created_rows': 0, 'confirmed_absent_rows': 0, 'unknown_rows': 0,
                          'unconfirmed_task_creations': 0,
                          'upload_attempted': False, 'object_versions_may_remain': False,
                          'retained_object_name': None},
              'not_covered': ['hosted-oidc-login-and-callback', 'session-expiry-and-logout',
                              'restart-and-restore', 'cloud-iam-and-network-isolation',
                              'deployed-source-or-image-identity', 'object-version-deletion']}
    users = {key: {'cookie': value} for key, value in (sessions or {}).items()}
    owned = []
    def record(name, status):
        result['checks'].append({'check': name, 'status': status})
        return status == 'passed'
    def expect(name, response, status, predicate=None):
        return record(name, 'passed' if response.status == status and (predicate is None or predicate(response)) else 'failed')
    def request(method, path, user=None, payload=None, *, binary=None, csrf=True, request_origin=None):
        headers = {}
        if user:
            headers['Cookie'] = users[user]['cookie']
            if method != 'GET':
                headers['Origin'] = request_origin or origin
                if csrf and users[user].get('csrf'):
                    headers['X-CSRF-Token'] = users[user]['csrf']
        body = binary
        if payload is not None:
            body = json.dumps(payload).encode(); headers['Content-Type'] = 'application/json'
        elif binary is not None:
            headers['Content-Type'] = 'application/octet-stream'
        return client.request(method, path, headers or None, body)
    def identifier(data):
        value = data.get('id') if isinstance(data, dict) else None
        if isinstance(value, bool) or not isinstance(value, int) or not ID.fullmatch(str(value)):
            raise CheckError('Synthetic resource identity could not be established.')
        return value
    try:
        initial = [expect('health', request('GET', '/healthz'), 200, lambda r: r.json() == {'status': 'ok'}),
                   expect('readiness', request('GET', '/readyz'), 200, lambda r: r.json() == {'status': 'ready'}),
                   expect('production-signed-out-session', request('GET', '/auth/session'), 200,
                          lambda r: r.json() == {'mode': 'production', 'authenticated': False}),
                   expect('unsigned-api-denied', request('GET', '/api/tasks'), 401)]
        if not exercise or not all(initial):
            record('authenticated-exercise', 'skipped')
            return finish(result)
        for user in ('a', 'b'):
            response = request('GET', '/auth/session', user)
            data = response.json()
            if not expect('authenticated-session-' + user, response, 200,
                          lambda r: isinstance(data, dict) and data.get('mode') == 'production'
                          and data.get('authenticated') is True and isinstance(data.get('csrfToken'), str)
                          and CSRF.fullmatch(data['csrfToken']) is not None):
                return finish(result)
            users[user]['csrf'] = data['csrfToken']
            cookies = [v for k, v in response.headers if k.lower() == 'set-cookie' and v.startswith('__Host-taskboard=')]
            flags = cookies[0].split(';') if len(cookies) == 1 else []
            attrs = {p.strip().lower() for p in flags[1:]}
            if not record('secure-session-cookie-' + user, 'passed' if flags and COOKIE.fullmatch(flags[0])
                          and {'secure', 'httponly', 'samesite=lax', 'path=/'}.issubset(attrs)
                          and not any(a.startswith('domain=') for a in attrs) else 'failed'):
                return finish(result)
            users[user]['cookie'] = flags[0]
        for user in ('a', 'b'):
            title = 'OCI acceptance ' + run_id + ' ' + user
            result['cleanup']['unconfirmed_task_creations'] += 1
            response = request('POST', '/api/tasks', user, {'title': title})
            if 400 <= response.status < 500:
                result['cleanup']['unconfirmed_task_creations'] -= 1
            if not expect('create-task-' + user, response, 201):
                return finish(result)
            data = response.json(); task_id = identifier(data)
            if data.get('title') != title:
                raise CheckError('Synthetic resource identity could not be established.')
            owned.append((user, task_id, title)); result['cleanup']['created_rows'] += 1
            result['cleanup']['unconfirmed_task_creations'] -= 1
        a, b = owned
        path = '/api/tasks/' + str(a[1])
        isolation = [expect('other-user-task-read-denied', request('GET', path, 'b'), 404),
                     expect('reciprocal-task-read-denied', request('GET', '/api/tasks/' + str(b[1]), 'a'), 404),
                     expect('other-user-task-update-denied', request('PATCH', path, 'b', {'done': True}), 404),
                     expect('other-user-task-delete-denied', request('DELETE', path, 'b'), 404)]
        listing = request('GET', '/api/tasks', 'b'); rows = listing.json()
        isolation.append(expect('other-user-list-isolation', listing, 200,
                                lambda r: isinstance(rows, list) and all(isinstance(row, dict) and row.get('id') != a[1] for row in rows)
                                and any(row.get('id') == b[1] for row in rows)))
        if not all(isolation):
            return finish(result)
        controls = [expect('missing-csrf-denied', request('PATCH', path, 'a', {'done': True}, csrf=False), 403),
                    expect('cross-origin-write-denied', request('PATCH', path, 'a', {'done': True}, request_origin='https://invalid.example'), 403),
                    expect('invalid-input-rejected', request('PATCH', path, 'a', {'title': ''}), 400),
                    expect('owner-update', request('PATCH', path, 'a', {'done': True}), 200,
                           lambda r: r.json().get('done') is True and r.json().get('id') == a[1])]
        if not all(controls):
            return finish(result)
        body = ('Synthetic acceptance bytes ' + run_id + '\n').encode()
        filename = 'acceptance-' + run_id + '.txt'
        metadata = {'filename': filename, 'size': len(body)}
        if not expect('other-user-upload-intent-denied', request('POST', path + '/attachments/upload-url', 'b', metadata), 404):
            return finish(result)
        upload = request('POST', path + '/attachments/upload-url', 'a', metadata)
        if not expect('owner-upload-intent', upload, 201):
            return finish(result)
        data = upload.json(); url = data.get('uploadUrl'); object_name = data.get('objectName')
        if (not isinstance(url, str) or not re.fullmatch(r'/api/uploads/[0-9a-f-]{36}', url)
                or not isinstance(object_name, str)
                or not re.fullmatch(r'tasks/' + str(a[1]) + r'/[0-9a-f-]{36}-' + re.escape(filename), object_name)):
            record('same-origin-proxy-upload-contract', 'failed'); return finish(result)
        record('same-origin-proxy-upload-contract', 'passed')
        result['cleanup']['retained_object_name'] = object_name
        result['cleanup']['upload_attempted'] = True
        result['cleanup']['object_versions_may_remain'] = True
        if not expect('other-user-upload-denied', request('PUT', url, 'b', binary=body), 404):
            return finish(result)
        if not expect('owner-proxy-upload', request('PUT', url, 'a', binary=body), 204):
            return finish(result)
        claim = request('POST', path + '/attachments', 'a', {**metadata, 'objectName': object_name})
        if not expect('owner-attachment-claim', claim, 201):
            return finish(result)
        attachment_id = identifier(claim.json())
        download = '/api/attachments/' + str(attachment_id) + '/download'
        expect('other-user-download-denied', request('GET', download, 'b'), 404)
        expect('unsigned-download-denied', request('GET', download), 401)
        expect('authenticated-proxy-file-bytes', request('GET', download, 'a'), 200,
               lambda r: r.body == body)
    except (CheckError, OSError, TypeError, AttributeError, KeyError):
        record('request-or-contract-incomplete', 'unknown')
    finally:
        for user, task_id, title in reversed(owned):
            path = '/api/tasks/' + str(task_id)
            try:
                current = request('GET', path, user)
                if current.status == 404:
                    absent = True
                else:
                    data = current.json()
                    if current.status != 200 or data.get('id') != task_id or data.get('title') != title:
                        raise CheckError('Cleanup identity could not be established.')
                    removed = request('DELETE', path, user)
                    absent = removed.status == 204 and request('GET', path, user).status == 404
                result['cleanup']['confirmed_absent_rows' if absent else 'unknown_rows'] += 1
            except (CheckError, OSError, TypeError, AttributeError, KeyError):
                result['cleanup']['unknown_rows'] += 1
        if owned:
            record('owned-task-row-cleanup', 'unknown' if result['cleanup']['unknown_rows'] else 'passed')
        finish(result)
    return finish(result)


def finish(result):
    statuses = {item['status'] for item in result['checks']}
    result['status'] = 'failed' if 'failed' in statuses else 'unknown' if 'unknown' in statuses else 'passed'
    result['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    return result


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'Invalid arguments; see --help. No input values are reported.\n')
    parser = Parser(description=__doc__)
    parser.add_argument('--url', required=True, help='Exact HTTPS origin; no path, query or credentials.')
    parser.add_argument('--exercise', action='store_true', help='Allow bounded synthetic task/file writes; use dedicated test users. Bucket objects/versions can remain.')
    parser.add_argument('--sessions-file', type=Path, help='Private mode-600 JSON outside Git; never pass cookies as arguments.')
    parser.add_argument('--ca-file', type=Path, help='Optional explicit private CA PEM file; verification stays enabled.')
    parser.add_argument('--out', type=Path, help='Create a new private sanitized report; never overwrite.')
    args = parser.parse_args(argv)
    output = None
    try:
        origin = validate_origin(args.url)
        if args.exercise != (args.sessions_file is not None):
            raise CheckError('Exercise and private test sessions must be selected together.')
        sessions = load_sessions(args.sessions_file, origin) if args.exercise else None
        if args.out:
            path = args.out.expanduser().absolute()
            if any(p.is_symlink() for p in (path, *path.parents)):
                raise CheckError('Report path is unsafe.')
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            output = os.fdopen(fd, 'w')
        report = run(origin, exercise=args.exercise, sessions=sessions, ca_file=args.ca_file)
        data = json.dumps(report, indent=2) + '\n'
        if output:
            output.write(data); output.flush()
        print(data, end='')
        return {'passed': 0, 'failed': 1, 'unknown': 3}[report['status']]
    except (CheckError, OSError, ValueError, UnicodeError, RecursionError):
        sys.stderr.write('Production check incomplete: verify the HTTPS target and private inputs. No input or response values are reported.\n')
        return 2
    finally:
        if output:
            output.close()


if __name__ == '__main__':
    raise SystemExit(main())
