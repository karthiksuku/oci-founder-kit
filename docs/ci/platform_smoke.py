"""Credential-free clean-install/archive/upgrade checks on hosted Linux and macOS."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '91af893a6ffd631ea98fd1c0727371083a5e6025'
BASELINES = {BASELINE: '0.5.0', 'c1f8de322564ac37693d25da8fa77f9daa266061': '0.6.0',
             'd36db320a9783e34e683376de6a363622bfb406a': '0.7.0',
             '3521de84ef7d8f459b60e266fa21e78af8df34ba': '0.8.0'}


def run(*args, expected=0):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != expected:
        raise SystemExit('Platform smoke command failed; no application or credential content is shown.')
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    baseline = args.baseline.resolve(strict=True)
    baseline_commit = run('git', '-C', baseline, 'rev-parse', 'HEAD').strip()
    if baseline_commit not in BASELINES:
        raise SystemExit('The upgrade baseline must be a reviewed v0.5.0, v0.6.0, v0.7.0 or v0.8.0 commit.')
    work = args.work.absolute()
    work.mkdir(mode=0o700, exist_ok=False)
    original = b'# Existing founder application, preserved during installation and upgrade.\n'
    clean = work / 'clean'
    clean.mkdir()
    (clean / 'application.py').write_bytes(original)
    run(sys.executable, ROOT / 'scripts/release_manifest.py', 'check')
    run(sys.executable, ROOT / 'scripts/release_archive.py', '--output-dir', work / 'assets')
    metadata = json.loads((work / 'assets/BUILD-METADATA.json').read_text())
    archive = work / 'assets' / metadata['archive']
    if hashlib.sha256(archive.read_bytes()).hexdigest() != metadata['sha256']:
        raise SystemExit('Archive identity mismatch.')
    unpack = work / 'unpacked'
    unpack.mkdir()
    with tarfile.open(archive) as bundle:
        bundle.extractall(unpack, filter='data')
    source = unpack / ('oci-founder-kit-' + metadata['version'])
    run(sys.executable, source / 'scripts/release_manifest.py', 'check')
    run(sys.executable, source / 'scripts/install.py', '--project', clean, '--agent', 'both')
    entry = clean / '.oci-founder-kit/scripts/kit.py'
    run(sys.executable, entry, 'start', '--project', clean, '--mode', 'existing', '--json', '--non-interactive')
    run(sys.executable, entry, 'capabilities', '--json')
    run(sys.executable, clean / '.oci-founder-kit/scripts/blueprint.py', 'check', 'web-container')
    run(sys.executable, clean / '.oci-founder-kit/scripts/blueprint.py', 'attach', 'web-container',
        '--project', clean, '--directory', 'deploy/oci')
    run(sys.executable, entry, 'environment', 'create', '--project', clean,
        '--environment', 'rehearsal', '--role', 'rehearsal', '--blueprint', 'web-container',
        '--infrastructure', 'deploy/oci/terraform', '--json')
    continued = json.loads(run(sys.executable, entry, 'next', '--project', clean, '--environment', 'rehearsal', '--json'))
    if continued.get('environment') != 'rehearsal':
        raise SystemExit('Installed continuation did not retain explicit environment selection.')
    run(sys.executable, entry, 'support', 'export', '--project', clean, '--environment', 'rehearsal', '--json')
    for command in ('architecture', 'journey'):
        report = json.loads(run(sys.executable, entry, command, '--project', clean,
                               '--environment', 'rehearsal', '--json', expected=3))
        if report.get('status') != 'incomplete' or report.get('environment') != 'rehearsal':
            raise SystemExit('Installed evidence report did not preserve incomplete acceptance.')
    report = json.loads(run(sys.executable, entry, 'release', 'configure', '--project', clean,
                           '--environment', 'rehearsal', '--json', expected=3))
    if report.get('status') != 'blocked' or report.get('cloud') != 'not_checked' or not report.get('missing'):
        raise SystemExit('Installed configuration handoff did not preserve missing prerequisites.')
    if (clean / 'application.py').read_bytes() != original:
        raise SystemExit('Clean install changed application source.')
    onboarding = work / 'onboarding'
    onboarding.mkdir()
    (onboarding / 'application.py').write_bytes(original)
    onboard_entry = source / 'scripts/kit.py'
    proposed = json.loads(run(sys.executable, onboard_entry, 'onboard', 'prepare', '--project', onboarding,
                             '--environment', 'rehearsal', '--role', 'rehearsal', '--dry-run', '--json'))
    if proposed.get('status') != 'proposed' or (onboarding / '.oci-founder-kit').exists():
        raise SystemExit('Onboarding preview mutated installation state.')
    prepared = json.loads(run(*proposed['next_action']['command'], '--json'))
    inspected = json.loads(run(*prepared['next_action']['command'], '--json'))
    if (prepared.get('status') != 'prepared' or inspected.get('environment') != 'rehearsal'
            or inspected.get('cloud') != 'not_checked' or (onboarding / 'application.py').read_bytes() != original):
        raise SystemExit('Clean onboarding or application preservation failed.')
    upgrade = work / 'upgrade'
    upgrade.mkdir()
    (upgrade / 'application.py').write_bytes(original)
    run(sys.executable, baseline / 'scripts/release_manifest.py', 'check')
    run(sys.executable, baseline / 'scripts/install.py', '--project', upgrade, '--agent', 'both')
    run(sys.executable, baseline / 'scripts/project.py', 'start', '--project', upgrade, '--mode', 'existing')
    legacy_state = (upgrade / '.oci-kit/state.json').read_bytes()
    run(sys.executable, source / 'scripts/update.py', 'check', '--project', upgrade)
    run(sys.executable, source / 'scripts/update.py', 'apply', '--project', upgrade)
    status = json.loads(run(sys.executable, source / 'scripts/install.py', '--status', '--project', upgrade))
    if status['kit_version'] != metadata['version'] or (upgrade / 'application.py').read_bytes() != original:
        raise SystemExit('Upgrade version or application-preservation mismatch.')
    if (upgrade / '.oci-kit/state.json').read_bytes() != legacy_state:
        raise SystemExit('Upgrade changed the saved project record.')
    run(sys.executable, upgrade / '.oci-founder-kit/scripts/kit.py', 'status', '--project', upgrade, '--json')
    run(sys.executable, upgrade / '.oci-founder-kit/scripts/kit.py', 'onboard', 'prepare', '--project', upgrade,
        '--environment', 'rehearsal', '--role', 'rehearsal', '--json')
    if (upgrade / '.oci-kit/state.json').read_bytes() != legacy_state or (upgrade / 'application.py').read_bytes() != original:
        raise SystemExit('Post-upgrade onboarding changed existing source or legacy records.')
    print(json.dumps({'schema': 'oci-kit-platform-smoke/1', 'status': 'passed',
                      'archive': 'verified', 'clean_install': 'passed', 'upgrade_from': BASELINES[baseline_commit],
                      'application_preserved': True, 'saved_records_preserved': True,
                      'installed_lifecycle_interface': 'passed', 'clean_and_upgraded_onboarding': 'passed', 'cloud': 'not_run'}))


if __name__ == '__main__':
    main()
