"""Trusted tagged release: draft, attach verified assets, read back, then publish.

No tags or assets are replaced. A failed run leaves its draft for owner review;
a retry must not erase evidence or silently reuse a partially populated draft.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('consumer_verifier', ROOT / 'scripts/verify_release.py')
verifier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verifier)


def run(*args):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=180, check=False)
    if result.returncode:
        raise SystemExit('Release step failed. Preserve the draft and assets for review; no replacement or deletion was attempted.')
    return result.stdout


def verify_tag(repo, tag, sha):
    item = json.loads(run('gh', 'api', 'repos/' + repo + '/git/ref/tags/' + tag))['object']
    if item.get('type') == 'tag':
        item = json.loads(run('gh', 'api', 'repos/' + repo + '/git/tags/' + item['sha']))['object']
    if item.get('type') != 'commit' or item.get('sha') != sha:
        raise SystemExit('The remote tag does not resolve to the reviewed source commit.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', required=True, type=Path)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--phase', required=True, choices=('draft', 'publish'))
    args = parser.parse_args(argv)
    repo, sha = os.environ.get('GH_REPO', ''), os.environ.get('GITHUB_SHA', '')
    if (os.environ.get('GITHUB_EVENT_NAME') != 'push' or os.environ.get('GITHUB_REF') != 'refs/tags/' + args.tag or
            not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or
            not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', args.tag) or not re.fullmatch(r'[0-9a-f]{40}', sha)):
        raise SystemExit('Publication requires the trusted protected-tag push workflow context.')
    record = json.loads((args.assets / 'BUILD-METADATA.json').read_text())
    names = verifier.expected_names(args.tag)
    if record.get('version') != args.tag[1:] or record.get('archive') != names[0]:
        raise SystemExit('Release assets do not match the reviewed tag.')
    verify_tag(repo, args.tag, sha)
    if args.phase == 'draft':
        # gh refuses an existing release. Do not treat lookup/network failure as
        # proof that a release is absent, and do not create a missing tag.
        run('gh', 'release', 'create', args.tag, '--repo', repo, '--draft', '--prerelease',
            '--verify-tag', '--latest=false', '--title', 'OCI Founder Kit ' + args.tag,
            '--notes-from-tag')
        print('Draft created; publication waits for attestation and downloaded-asset verification.')
        return
    public = json.loads(run('gh', 'release', 'view', args.tag, '--repo', repo, '--json', 'tagName,isDraft,assets'))
    if public.get('tagName') != args.tag or public.get('isDraft') is not True or public.get('assets') != []:
        raise SystemExit('Publication requires the exact empty draft. Preserve partial drafts for owner review.')
    verifier.verify(args.assets, repo, '.github/workflows/release.yml', args.tag, sha, record['sha256'])
    run('gh', 'release', 'upload', args.tag, '--repo', repo, *(args.assets / name for name in names))
    with tempfile.TemporaryDirectory(prefix='oci-kit-release-check-') as directory:
        for name in names:
            run('gh', 'release', 'download', args.tag, '--repo', repo, '--pattern', name, '--dir', directory)
        verifier.verify(Path(directory), repo, '.github/workflows/release.yml', args.tag, sha, record['sha256'])
    verify_tag(repo, args.tag, sha)
    public = json.loads(run('gh', 'release', 'view', args.tag, '--repo', repo, '--json', 'tagName,isDraft,assets'))
    if (public.get('isDraft') is not True or public.get('tagName') != args.tag or
            sorted(asset['name'] for asset in public.get('assets', [])) != sorted(names)):
        raise SystemExit('Draft changed during verification. Publication refused.')
    run('gh', 'release', 'edit', args.tag, '--repo', repo, '--draft=false', '--verify-tag', '--latest=false')
    final = json.loads(run('gh', 'release', 'view', args.tag, '--repo', repo, '--json', 'tagName,isDraft,assets'))
    if (final.get('isDraft') is not False or final.get('tagName') != args.tag or
            sorted(asset['name'] for asset in final.get('assets', [])) != sorted(names)):
        raise SystemExit('Post-publication readback failed; inspect the release, never replace its assets.')
    verify_tag(repo, args.tag, sha)
    print('Published preview: exact downloaded assets and authenticated source provenance verified. Latest pointer unchanged.')


if __name__ == '__main__':
    main()
