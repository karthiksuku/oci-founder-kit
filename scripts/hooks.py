#!/usr/bin/env python3
"""Optional, offline founder-kit checks. No cloud writes or transcript collection.

Run `staged` before committing or use the separately installed host adapters.
Hooks are supplementary guardrails, not a shell sandbox or proof of consent.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import threading
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
MAX_INPUT = 256 * 1024
MAX_BLOB = 2 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_FILES = 1024
CHECKS = {'secrets', 'readiness', 'validation', 'cloud', 'handoff'}
EVENTS = {'SessionStart', 'PreToolUse', 'PostToolUse', 'Stop'}
TOKEN_RULES = (
    ('private-key', re.compile(rb'-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----')),
    ('github-token', re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{24,}|github_pat_[A-Za-z0-9_]{30,})\b')),
    ('api-token', re.compile(rb'(?<![A-Za-z0-9_])(?:sk|xai)[-_][A-Za-z0-9_-]{24,}\b')),
    ('aws-access-key', re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
    ('private-oci-identity', re.compile(rb'ocid1\.(?:user|tenancy|credential)\.[a-z0-9-]+\.\.[a-z0-9]{20,}')),
)
ASSIGNMENT = re.compile(rb'''(?i)\b(?:password|passwd|client_secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b["']?\s*[:=]\s*["']([^\r\n"']{8,})["']''')
PLACEHOLDER = re.compile(rb'^(?:<[^<>]+>|\$\{[A-Z_][A-Z0-9_]*\}|(?:YOUR|REPLACE|EXAMPLE|PLACEHOLDER)[_-][A-Z0-9_-]+)$')


class CheckError(ValueError):
    """A bounded check could not establish a result; never includes source text."""


def bounded_read(path: Path, root: Path, limit: int = MAX_BLOB) -> bytes:
    """Read a regular file inside root without following any symlink component."""
    path = path.absolute()
    root = root.resolve(strict=True)
    if not path.is_relative_to(root):
        raise CheckError('outside project')
    for component in (path, *path.parents):
        if component == root:
            break
        if component.is_symlink():
            raise CheckError('symlink')
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)), 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise CheckError('not a regular file')
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise CheckError('file limit')
    return data


def run_git(project: Path, args: list[str], limit: int = MAX_BLOB, timeout: int = 5) -> bytes:
    """Fixed read commands only; bounded output, duration and no stderr disclosure."""
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update({'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'})
    proc = subprocess.Popen(['git', '-C', str(project), '--no-pager', *args],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL, env=env)
    expired = threading.Event()
    def expire():
        expired.set()
        proc.kill()
    timer = threading.Timer(timeout, expire)
    timer.daemon = True
    timer.start()
    try:
        data = proc.stdout.read(limit + 1)
        if len(data) > limit:
            proc.kill()
        code = proc.wait(timeout=2)
        if expired.is_set() or code or len(data) > limit:
            raise CheckError('Git check failed or exceeded limits')
        return data
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()


def private_path(name: str) -> bool:
    parts = Path(name).parts
    low = name.lower()
    base = Path(low).name
    if any(p.lower() in {'.oci', '.aws', '.gate', '.hooks', '.local-preview', 'credentials', 'private-receipts'} for p in parts):
        return True
    if low.endswith('.claude/settings.local.json'):
        return True
    if base in {'id_rsa', 'id_ed25519', 'credentials', 'token', 'tokens.json', 'crash.log', 'hook-installation.json'}:
        return True
    if base.startswith('.env') and base not in {'.env.example', '.env.sample', '.env.template'}:
        return True
    if base.endswith(('.pem', '.key', '.p12', '.pfx', '.tfvars', '.tfvars.json', '.tfplan', '.tfstate', '.tfbackend')):
        return True
    return '.tfstate.' in base or base.startswith('tfplan')


def display_path(name: str) -> str:
    """Filenames are data too; do not echo a recognizable token embedded in one."""
    for _, pattern in TOKEN_RULES:
        name = re.sub(pattern.pattern.decode('ascii'), '<redacted>', name)
    return name


def content_rules(data: bytes) -> list[str]:
    findings = [name for name, pattern in TOKEN_RULES if pattern.search(data)]
    if any(not PLACEHOLDER.fullmatch(match.group(1)) for match in ASSIGNMENT.finditer(data)):
        findings.append('literal-secret-assignment')
    return findings


def public_rules(data: bytes) -> list[str]:
    """Publication-only checks, not a policy imposed on private application work."""
    patterns = (
        ('private-workplace-url', rb'https?://[^\s/<>"\']*(?:oraclecorp[.]com|enterprise[.]slack[.]com)(?:[/\s<>"\']|$)'),
        ('local-home-path', rb'(?:/Users/|/home/)[A-Za-z0-9._-]+/'),
        ('local-windows-home', rb'[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s<]+[\\/]'),
    )
    return [name for name, pattern in patterns if re.search(pattern, data, re.I)]


def scan_staged(project: Path, *, public: bool = False, all_tracked: bool = False) -> dict:
    result = {'schema': 'oci-hook-check/1', 'status': 'passed', 'checked': 0, 'findings': [], 'incomplete': []}
    deadline = time.monotonic() + 8
    try:
        # The index belongs to the requested application, not an enclosing repo.
        actual = run_git(project, ['rev-parse', '--show-toplevel'], limit=16384).decode().strip()
        if Path(actual).resolve() != project.resolve():
            raise CheckError('use the Git repository root')
        names = run_git(project, ['ls-files', '-z'] if all_tracked else
                        ['diff', '--cached', '--name-only', '--diff-filter=ACMRT', '-z', '--'], limit=256 * 1024)
        selected = [name for name in names.split(b'\0') if name]
        if len(selected) > MAX_FILES:
            raise CheckError('staged file limit')
        total = 0
        for raw_name in selected:
            if time.monotonic() >= deadline:
                raise CheckError('check time limit')
            name = os.fsdecode(raw_name)
            if private_path(name):
                result['findings'].append({'path': display_path(name), 'rule': 'private-artifact'})
                continue
            entries = run_git(project, ['ls-files', '--stage', '-z', '--', name], limit=65536).split(b'\0')
            entry = next((x for x in entries if x and x.partition(b'\t')[2] == raw_name), None)
            if entry is None:
                raise CheckError('index changed during check')
            metadata = entry.partition(b'\t')[0].split()
            if len(metadata) != 3 or metadata[2] != b'0':
                raise CheckError('unmerged index')
            mode, oid, _ = metadata
            if mode == b'160000':
                result['incomplete'].append({'path': display_path(name), 'rule': 'submodule-not-scanned'})
                continue
            if not re.fullmatch(rb'[0-9a-f]{40,64}', oid):
                raise CheckError('invalid object id')
            size = int(run_git(project, ['cat-file', '-s', oid.decode()], limit=64))
            if size > MAX_BLOB or total + size > MAX_TOTAL:
                result['incomplete'].append({'path': display_path(name), 'rule': 'staged-byte-limit'})
                continue
            data = run_git(project, ['cat-file', 'blob', oid.decode()], limit=MAX_BLOB)
            total += len(data)
            result['checked'] += 1
            result['findings'].extend({'path': display_path(name), 'rule': rule} for rule in content_rules(data))
            if public:
                result['findings'].extend({'path': display_path(name), 'rule': rule} for rule in public_rules(data))
    except (OSError, ValueError, subprocess.SubprocessError):
        result['incomplete'].append({'path': '.', 'rule': 'git-check-unavailable'})
    result['status'] = 'blocked' if result['findings'] else 'incomplete' if result['incomplete'] else 'passed'
    return result


def finding_summary(result: dict) -> str:
    entries = result.get('findings', []) + result.get('incomplete', [])
    text = '; '.join(f"{json.dumps(x['path'], ensure_ascii=True)} ({x['rule']})" for x in entries[:8])
    return text + ('; further findings omitted' if len(entries) > 8 else '')


def _segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command.replace('\\\n', ''), posix=True, punctuation_chars=';&|\n')
    lexer.whitespace = ' \t\r'
    lexer.whitespace_split = True
    lexer.commenters = '#'
    segments, current = [], []
    for token in lexer:
        if token and all(c in ';&|\n' for c in token):
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _executable(tokens: list[str]) -> list[str]:
    tokens = list(tokens)
    while tokens:
        name = Path(tokens[0]).name
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', tokens[0]) or name in {'env', 'command', 'exec', 'nohup'}:
            tokens.pop(0)
        elif name in {'sudo', 'time'}:
            tokens.pop(0)
            while tokens and tokens[0].startswith('-'):
                option = tokens.pop(0)
                if option in {'-u', '-g', '-h'} and tokens:
                    tokens.pop(0)
        else:
            return [name, *tokens[1:]]
    return []


def cloud_reason(command: str, depth: int = 0) -> str | None:
    reason = 'Direct cloud mutation needs the reviewed oci-deploy workflow and explicit owner approval of its exact plan. This hook cannot grant approval.'
    if depth > 3 or len(command) > MAX_INPUT:
        return 'Command structure exceeds the hook limit; split it into simple reviewed commands.'
    try:
        segments = _segments(command)
    except ValueError:
        return 'Command could not be parsed; use a simple command so cloud-operation review can run.'
    for substitution in re.findall(r'\$\(([^()]*)\)|`([^`]*)`', command):
        if cloud_reason(next((x for x in substitution if x), ''), depth + 1):
            return reason
    for segment in segments:
        tokens = _executable(segment)
        if not tokens:
            continue
        executable, args = tokens[0], tokens[1:]
        if executable in {'bash', 'sh', 'zsh', 'dash'}:
            index = next((i for i, arg in enumerate(args) if arg == '--command' or re.fullmatch(r'-[a-z]*c[a-z]*', arg)), -1)
            if index >= 0 and index + 1 < len(args) and cloud_reason(args[index + 1], depth + 1):
                return reason
        if '--help' in args or '-h' in args or args == ['--version']:
            continue
        if executable in {'terraform', 'tofu'}:
            if any(a in {'apply', 'destroy', 'import', 'refresh', 'taint', 'untaint', 'force-unlock'} for a in args):
                return reason
            if 'state' in args and any(a in {'rm', 'mv', 'push', 'replace-provider'} for a in args):
                return reason
        elif executable == 'oci' and args:
            # Keep an explicit read-verb list. Unknown OCI operations need review.
            verbs = []
            index = 0
            while index < len(args):
                token = args[index]
                if token.startswith('-'):
                    index += 1 if '=' in token or token in {'--all', '--force', '--debug'} else 2
                else:
                    verbs.append(token)
                    index += 1
            reads = {'get', 'list', 'head', 'describe', 'search', 'structured-search', 'summarize', 'version'}
            mutations = {'create', 'update', 'delete', 'terminate', 'launch', 'put', 'upload', 'bulk-upload',
                         'bulk-delete', 'restore', 'move', 'change-compartment', 'action', 'authenticate', 'raw-request'}
            operation = verbs[-1] if verbs else ''
            if any(a in mutations for a in verbs) or not (operation in reads or operation.startswith('list-')):
                return reason
        elif executable in {'docker', 'podman'} and 'push' in args:
            return reason
        elif executable == 'skopeo':
            if 'delete' in args:
                return reason
            if 'copy' in args:
                transports = ('docker://', 'dir:', 'docker-archive:', 'oci:',
                              'oci-archive:', 'docker-daemon:', 'containers-storage:')
                references = [arg for arg in args if arg.startswith(transports)]
                if references and references[-1].startswith('docker://'):
                    return reason
        elif executable in {'kubectl', 'helm', 'pulumi'} and any(a in {'apply', 'delete', 'create', 'install', 'upgrade', 'uninstall', 'up', 'destroy'} for a in args):
            return reason
    return None


def _commit_command(command: str) -> tuple[bool, bool]:
    """Return commit detected and whether its current index can be checked reliably."""
    try:
        segments = _segments(command)
    except ValueError:
        return bool(re.search(r'\bgit\b.*\bcommit\b', command)), False
    commits = [s for s in segments if (t := _executable(s)) and t[0] == 'git' and 'commit' in t[1:]]
    if not commits:
        wrapped = any(_executable(s) and _executable(s)[0] in {'bash', 'sh', 'zsh', 'dash'} for s in segments)
        return wrapped and bool(re.search(r'\bgit\b[^\n]*\bcommit\b', command)), False
    tokens = commits[0]
    if len(segments) != 1 or tokens[:2] != ['git', 'commit']:
        return True, False
    args = tokens[2:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in {'-m', '--message', '-F', '--file'}:
            i += 2
            if i > len(args):
                return True, False
            continue
        if arg in {'--amend', '--no-edit', '-s', '--signoff', '-q', '--quiet', '--allow-empty', '--no-verify'} or arg.startswith(('--message=', '--file=', '--gpg-sign=')) or arg == '-S':
            i += 1
            continue
        return True, False
    return True, True


def validate_paths(project: Path, names: list[str], *, cache_path: Path | None = None) -> dict:
    cache = {}
    if cache_path is not None:
        try:
            loaded = json.loads(bounded_read(cache_path, ROOT, 32768))
            if isinstance(loaded, dict):
                cache = {k: v for k, v in loaded.items() if isinstance(k, str) and isinstance(v, dict)
                         and isinstance(v.get('at'), (float, int)) and isinstance(v.get('hash'), str)}
        except (OSError, ValueError):
            pass
    result = {'status': 'passed', 'checked': 0, 'skipped': 0, 'findings': []}
    for name in dict.fromkeys(names[:20]):
        path = Path(name)
        path = path if path.is_absolute() else project / path
        try:
            resolved = path.absolute()
            if '..' in path.parts or not resolved.is_relative_to(project.resolve()) or private_path(name):
                raise CheckError('private/outside')
            suffix = path.suffix.lower()
            if suffix not in {'.py', '.json', '.toml'} and path.name != 'SKILL.md':
                result['skipped'] += 1
                continue
            data = bounded_read(path, project, MAX_BLOB)
            key = hashlib.sha256(str(path).encode()).hexdigest()
            digest = hashlib.sha256(data).hexdigest()
            previous = cache.get(key, {})
            if previous.get('hash') == digest and 0 <= time.time() - previous.get('at', 0) < 2:
                result['skipped'] += 1
                continue
            cache[key] = {'hash': digest, 'at': time.time()}
            text = data.decode('utf-8')
            rel = path.relative_to(project).as_posix()
            result['checked'] += 1
            try:
                if suffix == '.py':
                    ast.parse(text)
                elif suffix == '.json':
                    json.loads(text)
                elif suffix == '.toml':
                    tomllib.loads(text)
                elif not (text.startswith('---\n') and '\n---\n' in text[4:]
                          and re.search(r'^name: [a-z0-9-]+$', text, re.M)
                          and re.search(r'^description: .+', text, re.M)):
                    result['findings'].append({'path': rel, 'rule': 'invalid-skill-frontmatter'})
            except (SyntaxError, ValueError, RecursionError):
                result['findings'].append({'path': rel, 'rule': 'invalid-' + suffix.lstrip('.')})
        except (OSError, ValueError, UnicodeError):
            result['skipped'] += 1
    result['status'] = 'warning' if result['findings'] else 'passed'
    if cache_path is not None:
        _save_validation_cache(cache_path, cache)
    return result


def _save_validation_cache(path: Path, cache: dict) -> None:
    # Advisory debounce only. Persist hashes/times, never source or transcripts.
    import tempfile
    temporary = None
    try:
        if path.parent.is_symlink() or not path.parent.is_dir() or path.is_symlink() or (path.exists() and not path.is_file()):
            return
        if not path.absolute().is_relative_to(ROOT):
            return
        for part in path.parents:
            if part == ROOT:
                break
            if part.is_symlink():
                return
        recent = dict(sorted(cache.items(), key=lambda item: item[1]['at'], reverse=True)[:64])
        fd, temporary = tempfile.mkstemp(prefix='.validation-', dir=path.parent)
        with os.fdopen(fd, 'w') as handle:
            json.dump(recent, handle)
        if not path.is_symlink():
            os.replace(temporary, path)
    except (OSError, ValueError, TypeError):
        pass
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def readiness(project: Path) -> str:
    version = 'unknown'
    try:
        manifest = json.loads(bounded_read(ROOT / 'plugin.json', ROOT, 32768))
        value = manifest.get('version', '')
        if isinstance(value, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?', value):
            version = value
    except (OSError, ValueError, AttributeError):
        pass
    missing = [name for name in ('git', 'node', 'oci', 'terraform') if shutil.which(name) is None]
    return (f'OCI Founder Kit {version}. Local tools missing: {", ".join(missing) or "none from the basic list"}. '
            'Local app development can begin before cloud setup. Use oci-ready for explicit credential/target checks; '
            'no authentication, permission or capacity checks ran in this hook. Cloud changes still require an approved exact plan.')


def respond(host: str, event: str, message: str, *, deny: bool = False) -> dict:
    if deny:
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                      'permissionDecisionReason': message}}
    if event in {'SessionStart', 'PreToolUse', 'PostToolUse'}:
        return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': message}}
    # Both hosts support a diagnostic message. No Stop decision/continuation loop.
    return {'systemMessage': message}


def changed_paths(tool_input: dict) -> list[str]:
    names = []
    for key in ('file_path', 'path'):
        if isinstance(tool_input.get(key), str):
            names.append(tool_input[key])
    command = tool_input.get('command', tool_input.get('patch', ''))
    if isinstance(command, str):
        names += re.findall(r'^\*\*\* (?:Add|Update|Delete) File: (.+)$', command, re.M)
        names += re.findall(r'^\*\*\* Move to: (.+)$', command, re.M)
    return names


def handle_event(project: Path, host: str, event: str, payload: dict, checks: set[str]) -> dict:
    if not isinstance(payload, dict) or payload.get('hook_event_name') != event:
        return respond(host, event, 'Hook input was invalid. Review the local hook setup.', deny=event == 'PreToolUse')
    if event == 'SessionStart' and 'readiness' in checks:
        return respond(host, event, readiness(project))
    if event == 'Stop' and 'handoff' in checks:
        return respond(host, event, 'Handoff: state what changed, actual checks, skipped/failed work and the next step. '
                       'Distinguish local builds, cloud plans, live deployment and production verification. This reminder is non-blocking.')
    inputs = payload.get('tool_input')
    if not isinstance(inputs, dict):
        return respond(host, event, 'Tool input was invalid; review the hook configuration.', deny=True) if event == 'PreToolUse' else {}
    name = payload.get('tool_name')
    if event == 'PreToolUse' and name in {'Bash', 'exec_command', 'shell', 'shell_command'}:
        command = inputs.get('command', inputs.get('cmd'))
        if isinstance(command, list) and all(isinstance(x, str) for x in command):
            command = shlex.join(command)
        if not isinstance(command, str):
            return respond(host, event, 'Shell input is unsupported; use a simple command.', deny=True)
        if 'cloud' in checks and (reason := cloud_reason(command)):
            return respond(host, event, reason, deny=True)
        commit, reliable = _commit_command(command)
        if 'secrets' in checks and commit:
            cwd = payload.get('cwd')
            if not reliable or not isinstance(cwd, str) or Path(cwd).resolve() != project.resolve():
                return respond(host, event, 'Stage files separately, then run a plain git commit from the configured repository root. '
                               'Combined staging, alternate indexes/directories and commit -a/path arguments cannot use this staged-byte check.', deny=True)
            result = scan_staged(project)
            if result['status'] != 'passed':
                return respond(host, event, 'Commit check needs attention: ' + finding_summary(result) +
                               '. Remove private artifacts or fix incomplete coverage, then retry. No secret values are shown.', deny=True)
        return {}  # Never grant permission; the normal host policy still applies.
    if event == 'PostToolUse' and 'validation' in checks:
        names = changed_paths(inputs)
        if names:
            result = validate_paths(project, names, cache_path=ROOT / '.hooks/validation-cache.json')
            if result['findings']:
                return respond(host, event, 'Offline syntax check: ' + finding_summary(result) + '. Fix these files before the next build. No app code was executed.')
    return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    for mode in ('staged', 'public', 'readiness', 'validate', 'event'):
        part = sub.add_parser(mode)
        part.add_argument('--project', type=Path, default=Path.cwd())
        if mode == 'validate':
            part.add_argument('paths', nargs='+')
        if mode == 'event':
            part.add_argument('--host', required=True, choices=('claude', 'codex'))
            part.add_argument('--event', required=True, choices=sorted(EVENTS))
            part.add_argument('--checks', default=','.join(sorted(CHECKS)))
            part.add_argument('--expected-sha256')
    args = parser.parse_args(argv)
    try:
        project = args.project.expanduser().resolve(strict=True)
        if not project.is_dir():
            raise CheckError('project missing')
        if args.mode in {'staged', 'public'}:
            result = scan_staged(project, public=args.mode == 'public', all_tracked=args.mode == 'public')
            print(json.dumps(result, indent=2, ensure_ascii=True))
            return 0 if result['status'] == 'passed' else 1
        if args.mode == 'readiness':
            print(readiness(project))
            return 0
        if args.mode == 'validate':
            result = validate_paths(project, args.paths)
            print(json.dumps(result, indent=2, ensure_ascii=True))
            return 1 if result['findings'] else 0
        if args.expected_sha256 and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != args.expected_sha256:
            raise CheckError('hook script changed; reinstall and review trust')
        checks = set(args.checks.split(','))
        if checks - CHECKS:
            raise CheckError('invalid checks')
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise CheckError('input limit')
        payload = json.loads(raw)
        result = handle_event(project, args.host, args.event, payload, checks)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (OSError, ValueError, RecursionError, subprocess.SubprocessError):
        if args.mode == 'event':
            print(json.dumps(respond(args.host, args.event, 'Founder Kit hook could not complete. Check local configuration and retry with a simple command.', deny=args.event == 'PreToolUse')))
            return 0
        sys.stderr.write('Check incomplete: verify the local project, Git index and file limits. No source values are reported.\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
