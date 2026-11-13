#!/usr/bin/env python3
"""Install/remove optional project-local Claude Code and Codex hooks.

No global changes, cloud calls, dependency installation or automatic hook trust.
Run with --dry-run to inspect the proposed local settings before opting in.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {'claude': '.claude/settings.local.json', 'codex': '.codex/hooks.json'}
CHECKS = {'secrets', 'readiness', 'validation', 'cloud', 'handoff'}
LIMIT = 1024 * 1024


def safe_path(path: Path, project: Path) -> None:
    if not path.is_relative_to(project):
        raise ValueError('outside project')
    for part in (path, *path.parents):
        if part == project:
            break
        if part.is_symlink() or (part != path and part.exists() and not part.is_dir()):
            raise ValueError('unsafe path')


def raw_file(path: Path, project: Path) -> bytes | None:
    safe_path(path, project)
    if not path.exists():
        return None
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)), 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError('not regular')
        data = handle.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError('file limit')
    return data


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def object_file(path: Path, project: Path) -> tuple[dict, bytes | None]:
    raw = raw_file(path, project)
    data = json.loads(raw, object_pairs_hook=_unique) if raw is not None else {}
    if not isinstance(data, dict):
        raise ValueError('expected JSON object')
    return data, raw


def validate_config(data: dict) -> None:
    hooks = data.get('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('hooks must be object')
    for groups in hooks.values():
        if not isinstance(groups, list):
            raise ValueError('event must be array')
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get('hooks'), list):
                raise ValueError('invalid matcher group')
            if any(not isinstance(handler, dict) for handler in group['hooks']):
                raise ValueError('invalid handler')


def layout(project: Path) -> tuple[Path, Path]:
    bundle = project if project == ROOT else project / '.oci-founder-kit'
    script = bundle / 'scripts/hooks.py'
    raw = raw_file(script, project)
    if raw is None:
        raise ValueError('install the kit in this project first')
    return script, bundle / '.hooks'


def selected(agent: str) -> list[str]:
    if agent == 'both':
        return list(CONFIG)
    if agent not in CONFIG:
        raise ValueError('unknown agent')
    return [agent]


def generated(project: Path, script: Path, host: str, checks: set[str], digest: str) -> dict:
    events = {}
    wanted = [('SessionStart', None, 'readiness'),
              ('PreToolUse', 'Bash|exec_command|shell|shell_command', 'secrets'),
              ('PostToolUse', 'Write|Edit|MultiEdit|apply_patch', 'validation'),
              ('Stop', None, 'handoff')]
    for event, matcher, check in wanted:
        if check not in checks and not (event == 'PreToolUse' and 'cloud' in checks):
            continue
        args = [sys.executable, str(script), 'event', '--project', str(project),
                '--host', host, '--event', event, '--checks', ','.join(sorted(checks)),
                '--expected-sha256', digest]
        handler = {'type': 'command', 'command': shlex.join(args), 'timeout': 15}
        group = {'hooks': [handler]}
        if matcher:
            group['matcher'] = matcher
        events[event] = [group]
    return events


def encoded(data: dict) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=True) + '\n').encode()


def replace_file(path: Path, project: Path, before: bytes | None, after: bytes | None) -> None:
    safe_path(path, project)
    if raw_file(path, project) != before:
        raise ValueError('file changed concurrently')
    if after is None:
        if before is not None:
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_path(path, project)
    fd, temporary = tempfile.mkstemp(prefix='.oci-hooks-', dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, 'wb') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(after)
            handle.flush()
            os.fsync(handle.fileno())
        if raw_file(path, project) != before:
            raise ValueError('file changed concurrently')
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def transact(project: Path, writes: list[tuple[Path, bytes | None, bytes | None]]) -> None:
    applied = []
    try:
        for path, before, after in writes:
            replace_file(path, project, before, after)
            applied.append((path, before, after))
    except Exception:
        # Restore only our own exact writes. Never clobber a concurrent edit.
        for path, before, after in reversed(applied):
            try:
                replace_file(path, project, after, before)
            except (OSError, ValueError):
                pass
        raise


def install(project: Path, agent: str, dry_run: bool = False, checks: set[str] | None = None) -> dict:
    project = project.expanduser().resolve(strict=True)
    if os.name == 'nt':
        raise ValueError('use WSL for shell adapters')
    checks = CHECKS if checks is None else checks
    if not checks or checks - CHECKS:
        raise ValueError('unknown checks')
    script, metadata = layout(project)
    digest = hashlib.sha256(raw_file(script, project)).hexdigest()
    writes = []
    for host in selected(agent):
        config = project / CONFIG[host]
        record = metadata / f'{host}.json'
        if raw_file(record, project) is not None:
            raise ValueError('hooks already installed; inspect/uninstall first')
        data, before = object_file(config, project)
        validate_config(data)
        owned = generated(project, script, host, checks, digest)
        merged = copy.deepcopy(data)
        for event, groups in owned.items():
            existing = merged.setdefault('hooks', {}).setdefault(event, [])
            if any(group in existing for group in groups):
                raise ValueError('matching unmanaged hook already present')
            existing.extend(groups)
        registration = {'schema': 'oci-hook-install/1', 'host': host,
                        'config_existed': before is not None, 'hooks_existed': 'hooks' in data,
                        'original_events': list(data.get('hooks', {})),
                        'owned': owned, 'checks': sorted(checks), 'script_sha256': digest}
        writes.extend([(config, before, encoded(merged)), (record, None, encoded(registration))])
    ignore = metadata / '.gitignore'
    existing_ignore = raw_file(ignore, project)
    if existing_ignore is None:
        writes.append((ignore, None, b'*\n'))
    result = {'schema': 'oci-hook-install/1', 'agents': selected(agent), 'checks': sorted(checks),
              'dry_run': dry_run, 'trust_review_required': True,
              'settings': [CONFIG[host] for host in selected(agent)],
              'next': 'Review commands in /hooks in each host and restart after trusting. No trust settings were changed. Keep generated local settings out of Git.'}
    if not dry_run:
        transact(project, writes)
    return result


def uninstall(project: Path, agent: str, dry_run: bool = False) -> dict:
    project = project.expanduser().resolve(strict=True)
    script, metadata = layout(project)
    writes = []
    for host in selected(agent):
        record = metadata / f'{host}.json'
        registration, record_before = object_file(record, project)
        if registration.get('schema') != 'oci-hook-install/1' or registration.get('host') != host:
            raise ValueError('no matching hook registration')
        checks = set(registration.get('checks', []))
        digest = registration.get('script_sha256', '')
        if not checks or checks - CHECKS or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError('invalid registration')
        if registration.get('owned') != generated(project, script, host, checks, digest):
            raise ValueError('registration does not describe generated local hooks')
        config = project / CONFIG[host]
        data, before = object_file(config, project)
        validate_config(data)
        merged = copy.deepcopy(data)
        owned = registration.get('owned')
        if not isinstance(owned, dict):
            raise ValueError('invalid registration')
        for event, groups in owned.items():
            if not isinstance(groups, list) or not isinstance(merged.get('hooks', {}).get(event), list):
                raise ValueError('owned event missing or changed; review manually')
            existing = merged['hooks'][event]
            for group in groups:
                if group not in existing:
                    raise ValueError('owned hook changed; review manually')
                existing.remove(group)
            if not existing and event not in registration.get('original_events', []):
                del merged['hooks'][event]
        if not merged.get('hooks') and not registration.get('hooks_existed'):
            merged.pop('hooks', None)
        after = encoded(merged) if merged or registration.get('config_existed') else None
        writes.extend([(config, before, after), (record, record_before, None)])
    if not dry_run:
        transact(project, writes)
    return {'schema': 'oci-hook-uninstall/1', 'agents': selected(agent), 'dry_run': dry_run,
            'next': 'Restart the coding agents. Existing unrelated hooks and settings were preserved.'}


def status(project: Path, agent: str) -> dict:
    project = project.expanduser().resolve(strict=True)
    script, metadata = layout(project)
    digest = hashlib.sha256(raw_file(script, project)).hexdigest()
    agents = []
    for host in selected(agent):
        registration, raw = object_file(metadata / f'{host}.json', project)
        state = 'not-installed' if raw is None else 'installed-needs-host-trust-check'
        if raw is not None:
            config, _ = object_file(project / CONFIG[host], project)
            validate_config(config)
            if registration.get('script_sha256') != digest:
                state = 'script-changed'
            elif any(group not in config.get('hooks', {}).get(event, [])
                     for event, groups in registration.get('owned', {}).items() for group in groups):
                state = 'configuration-changed'
        agents.append({'agent': host, 'status': state})
    return {'schema': 'oci-hook-status/1', 'agents': agents,
            'note': 'This inspects local registration, not host trust or cloud access.'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'uninstall', 'status'))
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--agent', choices=('claude', 'codex', 'both'), default='both')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--checks', default=','.join(sorted(CHECKS)))
    args = parser.parse_args(argv)
    try:
        if args.action == 'install':
            result = install(args.project, args.agent, args.dry_run, set(args.checks.split(',')))
        elif args.action == 'uninstall':
            result = uninstall(args.project, args.agent, args.dry_run)
        else:
            result = status(args.project, args.agent)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, RecursionError, TypeError):
        sys.stderr.write('Hook setup refused: verify the installed kit, project-local JSON settings, safe paths and existing registration. '
                         'Inspect status before reinstalling; modified owned entries require manual review. No global configuration or trust was changed.\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
