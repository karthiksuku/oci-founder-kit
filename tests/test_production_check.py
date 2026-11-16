"""Production acceptance input/transport contracts; synthetic values only."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'blueprints/fullstack-container/production_check.py'
spec = importlib.util.spec_from_file_location('production_check', SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class Inputs(unittest.TestCase):
    def load(self, path, origin):
        with mock.patch.object(check, 'inside_git', return_value=False):
            return check.load_sessions(path, origin)

    def test_only_exact_https_origins_are_accepted(self):
        self.assertEqual(check.validate_origin('https://example.test:8443'), 'https://example.test:8443')
        for value in ('http://example.test', 'https://user:pass@example.test', 'https://example.test/path',
                      'https://example.test?token=anything', 'https://example.test#fragment',
                      'https://example.test\\other', 'https://example.test\n', 'https://example.test:0',
                      'https://example.test:', 'https://example.test?', 'https://example.test#'):
            with self.subTest(value=value), self.assertRaises(check.CheckError):
                check.validate_origin(value)

    def test_sessions_require_private_regular_file_and_exact_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'sessions.json'
            data = {'schema': 'oci-production-sessions/1', 'origin': 'https://example.test',
                    'users': {'a': '__Host-taskboard=' + 'a' * 32, 'b': '__Host-taskboard=' + 'b' * 32}}
            path.write_text(json.dumps(data)); path.chmod(0o600)
            # Some test hosts keep /tmp in a Git worktree. Input parsing remains
            # independent of that host layout; repository refusal is checked below.
            self.assertEqual(set(self.load(path, data['origin'])), {'a', 'b'})
            with self.assertRaises(check.CheckError):
                self.load(path, 'https://other.test')
            path.chmod(0o644)
            with self.assertRaises(check.CheckError):
                self.load(path, data['origin'])
            path.chmod(0o600)
            link = root / 'link'; link.symlink_to(path)
            with self.assertRaises(check.CheckError):
                self.load(link, data['origin'])
            (root / '.git').mkdir()
            with self.assertRaises(check.CheckError):
                check.load_sessions(path, data['origin'])

    def test_cookie_header_injection_duplicate_users_and_unknown_fields_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sessions.json'
            for users in ({'a': '__Host-taskboard=' + 'a' * 32, 'b': '__Host-taskboard=' + 'a' * 32},
                          {'a': '__Host-taskboard=' + 'a' * 32, 'b': 'cookie\r\nInjected: value'},
                          {'a': '__Host-taskboard=' + 'a' * 32, 'b': '__Host-taskboard=' + 'b' * 32 + '; other=value'}):
                path.write_text(json.dumps({'schema': 'oci-production-sessions/1',
                                           'origin': 'https://example.test', 'users': users}))
                path.chmod(0o600)
                with self.assertRaises(check.CheckError):
                    self.load(path, 'https://example.test')

    def test_existing_or_symlink_report_is_refused_before_target_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / 'report.json'; existing.write_text('unchanged')
            link = Path(tmp) / 'link'; link.symlink_to(existing)
            for path in (existing, link):
                with mock.patch.object(check, 'run') as run, redirect_stderr(io.StringIO()):
                    self.assertEqual(check.main(['--url', 'https://example.test', '--out', str(path)]), 2)
                    run.assert_not_called()
            self.assertEqual(existing.read_text(), 'unchanged')

    def test_private_input_duplicate_unknown_fields_and_size_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sessions.json'
            for raw in ('{"schema":1,"schema":2}', 'x' * 17000,
                        json.dumps({'schema': 'oci-production-sessions/1', 'origin': 'https://example.test',
                                    'users': {'a': '__Host-taskboard=' + 'a' * 32, 'b': '__Host-taskboard=' + 'b' * 32},
                                    'extra': 'refused'})):
                path.write_text(raw); path.chmod(0o600)
                with self.assertRaises(check.CheckError):
                    self.load(path, 'https://example.test')


class ReadOnly(unittest.TestCase):
    class Client:
        def __init__(self, sandbox=False, fail=False):
            self.calls = []; self.sandbox = sandbox; self.fail = fail

        def request(self, method, path, headers=None, body=None):
            self.calls.append((method, path, headers, body))
            if self.fail:
                raise check.CheckError('transport unavailable')
            data = {'/healthz': {'status': 'ok'}, '/readyz': {'status': 'ready'},
                    '/auth/session': {'mode': 'sandbox' if self.sandbox else 'production',
                                      'authenticated': self.sandbox}, '/api/tasks': {'error': 'sign in'}}
            status = 401 if path == '/api/tasks' else 200
            return check.Response(status, [], json.dumps(data[path]).encode())

    def test_default_makes_only_anonymous_reads_and_does_not_claim_production_ready(self):
        client = self.Client()
        result = check.run('https://example.test', client=client)
        self.assertEqual(result['status'], 'passed')
        self.assertTrue(all(method == 'GET' and not headers and body is None
                            for method, path, headers, body in client.calls))
        self.assertFalse(result['production_readiness_established'])
        self.assertIn('restart-and-restore', result['not_covered'])

    def test_sandbox_and_unavailable_target_cannot_pass(self):
        self.assertEqual(check.run('https://example.test', client=self.Client(sandbox=True))['status'], 'failed')
        self.assertEqual(check.run('https://example.test', client=self.Client(fail=True))['status'], 'unknown')

    def test_stalled_resolver_does_not_start_http_request(self):
        def delayed(*args, **kwargs):
            time.sleep(0.2)
            return []
        client = check.HTTPSClient('https://example.test')
        client.deadline = time.monotonic() + 0.05
        with mock.patch.object(check.socket, 'getaddrinfo', side_effect=delayed), \
                mock.patch.object(check.http.client.HTTPSConnection, 'request') as request:
            result = check.run('https://example.test', client=client)
            self.assertEqual(result['status'], 'unknown')
            request.assert_not_called()


@unittest.skipUnless(os.environ.get('FOUNDER_KIT_PRODUCTION_CHECK_LOCAL') == '1',
                     'Opt-in real local TLS/app exercise; no dependencies installed by tests.')
class LocalApplication(unittest.TestCase):
    @contextmanager
    def server(self, fault='none', remaining=1):
        self.assertIsNotNone(shutil.which('node'))
        self.assertIsNotNone(shutil.which('openssl'))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); key = folder / 'key.pem'; cert = folder / 'ca.pem'
            tls = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                                  '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                                  '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
                                 capture_output=True, timeout=30)
            self.assertEqual(tls.returncode, 0)
            key.chmod(0o600); cert.chmod(0o600)
            ready = folder / 'ready.json'; final = folder / 'final.json'
            proc = subprocess.Popen(['node', str(ROOT / 'tests/fixtures/production_check_server.mjs'),
                                     str(key), str(cert), str(ready), str(final), fault],
                                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.03)
                self.assertTrue(ready.exists(), 'Local application fixture did not start')
                data = json.loads(ready.read_bytes())
                yield data, cert, final
            finally:
                proc.stdin.close()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.terminate(); proc.wait(timeout=3)
                self.assertEqual(proc.returncode, 0)
            state = json.loads(final.read_bytes())
            self.assertTrue(state['foreignUnchanged'])
            self.assertEqual(state['remainingRows'], remaining)
            self.assertFalse(state['parCreated'])

    def test_real_https_app_auth_isolation_files_and_owned_cleanup(self):
        with self.server() as (data, cert, final):
            result = check.run(data['origin'], exercise=True, sessions=data['users'], ca_file=cert)
            self.assertEqual(result['status'], 'passed', result['checks'])
            self.assertEqual(result['cleanup']['created_rows'], 2)
            self.assertEqual(result['cleanup']['confirmed_absent_rows'], 2)
            self.assertTrue(result['cleanup']['object_versions_may_remain'])
            self.assertRegex(result['cleanup']['retained_object_name'],
                             r'^tasks/[1-9][0-9]*/[0-9a-f-]{36}-acceptance-' + result['run_id'] + r'\.txt$')
            for cookie in data['users'].values():
                self.assertNotIn(cookie, json.dumps(result))
            self.assertNotIn(data['origin'], json.dumps(result))
            self.assertFalse(result['production_readiness_established'])

    def test_actual_missing_csrf_control_is_detected(self):
        with self.server('missing-csrf-control') as (data, cert, final):
            result = check.run(data['origin'], exercise=True, sessions=data['users'], ca_file=cert)
            self.assertEqual(result['status'], 'failed')
            self.assertIn({'check': 'missing-csrf-denied', 'status': 'failed'}, result['checks'])
            self.assertIn({'check': 'cross-origin-write-denied', 'status': 'failed'}, result['checks'])

    def test_certificate_verification_remains_required(self):
        with self.server() as (data, cert, final):
            result = check.run(data['origin'])
            self.assertEqual(result['status'], 'unknown')
            self.assertEqual(result['cleanup']['created_rows'], 0)

    def test_no_redirect_following_or_oversize_success(self):
        for fault, expected in [('redirect-ready', 'failed'), ('oversize-ready', 'unknown')]:
            with self.subTest(fault=fault), self.server(fault) as (data, cert, final):
                result = check.run(data['origin'], ca_file=cert)
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['cleanup']['created_rows'], 0)

    def test_lost_create_response_is_unknown_and_not_blindly_deleted(self):
        with self.server(remaining=2) as (data, cert, final):
            real = check.HTTPSClient(data['origin'], cert)
            class Lost:
                def request(self, method, path, headers=None, body=None):
                    response = real.request(method, path, headers, body)
                    if method == 'POST' and path == '/api/tasks':
                        raise check.CheckError('Synthetic lost response')
                    return response
            result = check.run(data['origin'], exercise=True, sessions=data['users'], client=Lost())
            self.assertEqual(result['status'], 'unknown')
            self.assertEqual(result['cleanup']['unconfirmed_task_creations'], 1)
            self.assertEqual(result['cleanup']['confirmed_absent_rows'], 0)

    def test_cleanup_refuses_changed_row_identity(self):
        with self.server(remaining=2) as (data, cert, final):
            real = check.HTTPSClient(data['origin'], cert)
            class Changed:
                changed = False
                def request(self, method, path, headers=None, body=None):
                    response = real.request(method, path, headers, body)
                    if not self.changed and method == 'GET' and check.re.fullmatch(r'/api/tasks/\d+', path) and response.status == 200:
                        self.changed = True
                        value = response.json(); value['title'] = 'different row; preserve'
                        return check.Response(200, response.headers, json.dumps(value).encode())
                    return response
            result = check.run(data['origin'], exercise=True, sessions=data['users'], client=Changed())
            self.assertEqual(result['status'], 'unknown')
            self.assertEqual(result['cleanup']['unknown_rows'], 1)
            self.assertEqual(result['cleanup']['confirmed_absent_rows'], 1)

    def test_external_upload_url_is_refused_before_upload(self):
        with self.server() as (data, cert, final):
            real = check.HTTPSClient(data['origin'], cert)
            class External:
                puts = 0
                def request(self, method, path, headers=None, body=None):
                    self.puts += method == 'PUT'
                    response = real.request(method, path, headers, body)
                    if path.endswith('/attachments/upload-url') and response.status == 201:
                        value = response.json(); value['uploadUrl'] = 'https://uncontacted.example.invalid/upload'
                        return check.Response(201, response.headers, json.dumps(value).encode())
                    return response
            client = External()
            result = check.run(data['origin'], exercise=True, sessions=data['users'], client=client)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(client.puts, 0)
            self.assertFalse(result['cleanup']['upload_attempted'])
            self.assertIsNone(result['cleanup']['retained_object_name'])

    def test_stalled_response_obeys_total_deadline(self):
        with self.server('slow-ready') as (data, cert, final):
            client = check.HTTPSClient(data['origin'], cert)
            client.deadline = time.monotonic() + 0.3
            started = time.monotonic()
            result = check.run(data['origin'], client=client)
            self.assertEqual(result['status'], 'unknown')
            self.assertLess(time.monotonic() - started, 2)

    def test_cli_read_only_report_is_private_sanitized_and_source_bound(self):
        with self.server() as (data, cert, final):
            output = final.parent / 'report.json'; stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = check.main(['--url', data['origin'], '--ca-file', str(cert), '--out', str(output)])
            self.assertEqual(code, 0)
            report = json.loads(output.read_bytes())
            self.assertEqual(json.loads(stdout.getvalue()), report)
            self.assertNotIn(data['origin'], output.read_text())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(report['runner_sha256'], check.hashlib.sha256(SCRIPT.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
