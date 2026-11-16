"""Trusted release-job publication and independent download/attestation checks.

Run only after the tagged source passed validation and GitHub generated its
attestations. Never overwrite an existing asset; a partial upload remains visible
for owner review. The workflow is the authorization boundary for these writes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def run(*args):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=180, check=False)
    if result.returncode:
        raise SystemExit('Release publication/verification failed. Existing assets remain for review; no replacement or deletion was attempted.')
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', required=True, type=Path)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    repo = os.environ.get('GH_REPO', '')
    sha = os.environ.get('GITHUB_SHA', '')
    if (os.environ.get('GITHUB_EVENT_NAME') != 'release' or
            not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or
            not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', args.tag) or
            not re.fullmatch(r'[0-9a-f]{40}', sha)):
        raise SystemExit('Publication requires the trusted tagged-release workflow context.')
    record = json.loads((args.assets / 'BUILD-METADATA.json').read_text())
    expected_archive = 'oci-founder-kit-' + args.tag[1:] + '.tar.gz'
    names = [expected_archive, 'release-manifest.json', 'BUILD-METADATA.json', 'SHA256SUMS']
    if record.get('version') != args.tag[1:] or record.get('archive') != expected_archive:
        raise SystemExit('Release assets do not match the approved tag.')
    public = json.loads(run('gh', 'release', 'view', args.tag, '--repo', repo, '--json', 'tagName,isDraft'))
    if public.get('tagName') != args.tag or public.get('isDraft'):
        raise SystemExit('The exact tagged release must already be published.')
    # Fail before uploading if an asset changed after attestation generation.
    for name in names:
        path = args.assets / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit('Unsafe release asset.')
        run('gh', 'attestation', 'verify', path, '--repo', repo,
            '--signer-workflow', repo + '/.github/workflows/release.yml',
            '--source-ref', 'refs/tags/' + args.tag, '--source-digest', sha, '--deny-self-hosted-runners')
    run('gh', 'release', 'upload', args.tag, '--repo', repo, *(args.assets / name for name in names))
    with tempfile.TemporaryDirectory(prefix='oci-kit-release-check-') as directory:
        for name in names:
            run('gh', 'release', 'download', args.tag, '--repo', repo, '--pattern', name, '--dir', directory)
            actual = (Path(directory) / name).read_bytes()
            expected = (args.assets / name).read_bytes()
            if hashlib.sha256(actual).digest() != hashlib.sha256(expected).digest():
                raise SystemExit('Published release bytes differ; inspect the partial release.')
    print('Published assets match the exact tagged source and verified GitHub workflow attestations.')


if __name__ == '__main__':
    main()
