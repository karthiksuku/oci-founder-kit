"""Release packaging follows a verified allowlist and has reproducible public bytes."""
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


archive = module('release_archive_test', ROOT / 'scripts/release_archive.py')


class ReleaseArchive(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oci-kit-archive-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'kit'
        (self.root / 'scripts').mkdir(parents=True)
        for name in ('install.py', 'release_manifest.py'):
            shutil.copyfile(ROOT / 'scripts' / name, self.root / 'scripts' / name)
        (self.root / '.claude-plugin').mkdir()
        (self.root / '.claude-plugin/plugin.json').write_text('{"version":"9.8.7"}\n')
        (self.root / 'skills/example').mkdir(parents=True)
        (self.root / 'skills/example/SKILL.md').write_text('---\nname: example\ndescription: Public example\n---\nUse the reviewed workflow.\n')
        (self.root / 'LICENSE').write_text('Synthetic license fixture\n')
        self.names = [p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file()]
        installer, manifest = archive.helpers(self.root)
        manifest.write(self.root, manifest.build(self.root, self.names, installer.distributable))

    def build(self, name='assets'):
        destination = self.base / name
        return archive.build(self.root, destination), destination

    def test_same_bytes_across_file_mtimes_locations_and_permissions(self):
        first, path = self.build('first')
        original = (path / first['archive']).read_bytes()
        for file in self.root.rglob('*'):
            if file.is_file():
                os.utime(file, (1234567890, 1234567890))
                file.chmod(0o600)
        moved = self.base / 'different-public-source'
        shutil.copytree(self.root, moved)
        second = archive.build(moved, self.base / 'second')
        self.assertEqual(first, second)
        self.assertEqual(original, (self.base / 'second' / second['archive']).read_bytes())
        with tarfile.open(path / first['archive']) as packed:
            for member in packed:
                self.assertEqual((member.uid, member.gid, member.mtime, member.uname, member.gname), (0, 0, 0, '', ''))
                self.assertTrue(member.isfile())

    def test_unlisted_private_files_do_not_enter_archive_or_reports(self):
        (self.root / 'skills/example/unreviewed.json').write_text('PRIVATE_TEST_SENTINEL')
        (self.root / 'skills/example/.env').write_text('PRIVATE_TEST_SENTINEL')
        (self.root / '.git').mkdir()
        (self.root / '.git/config').write_text('PRIVATE_TEST_SENTINEL')
        report, output = self.build()
        raw = gzip.decompress((output / report['archive']).read_bytes())
        self.assertNotIn(b'PRIVATE_TEST_SENTINEL', raw)
        self.assertNotIn(str(self.base).encode(), raw)
        self.assertNotIn(str(self.base), json.dumps(report))
        for name in ('BUILD-METADATA.json', 'SHA256SUMS', 'release-manifest.json'):
            self.assertNotIn(b'PRIVATE_TEST_SENTINEL', (output / name).read_bytes())

    def test_changed_manifest_bytes_refuse_before_output(self):
        (self.root / 'LICENSE').write_text('Changed since manifest review')
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.base / 'assets').exists())

    def test_missing_manifest_never_falls_back_to_directory_copy(self):
        (self.root / 'release-manifest.json').unlink()
        with self.assertRaises(OSError):
            self.build()
        self.assertFalse((self.base / 'assets').exists())

    def test_source_symlink_and_symlinked_output_are_refused(self):
        target = self.root / 'LICENSE'
        external = self.base / 'outside-license'
        external.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(external)
        with self.assertRaises(ValueError):
            self.build()
        target.unlink()
        target.write_bytes(external.read_bytes())
        outside = self.base / 'outside'
        outside.mkdir()
        linked = self.base / 'linked'
        linked.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            archive.build(self.root, linked / 'assets')
        self.assertEqual(list(outside.iterdir()), [])

    def test_private_manifest_paths_are_refused_even_when_hashed(self):
        content = {'schema': 'oci-kit-release/1', 'files': {'skills/example/.env': {
            'sha256': hashlib.sha256(b'PRIVATE_TEST_SENTINEL').hexdigest(), 'executable': False}}}
        (self.root / 'skills/example/.env').write_text('PRIVATE_TEST_SENTINEL')
        (self.root / 'release-manifest.json').write_text(json.dumps(content))
        with self.assertRaises(ValueError):
            self.build()

    def test_existing_output_and_source_overlap_are_never_overwritten(self):
        self.build()
        before = {p.name: p.read_bytes() for p in (self.base / 'assets').iterdir()}
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.base / 'assets').iterdir()})
        with self.assertRaises(ValueError):
            archive.build(self.root, self.root / 'release')

    def test_checksums_and_installation_from_extracted_archive(self):
        report, output = self.build()
        for line in (output / 'SHA256SUMS').read_text().splitlines():
            checksum, name = line.split('  ', 1)
            self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), checksum)
        unpack = self.base / 'unpacked'
        unpack.mkdir()
        with tarfile.open(output / report['archive']) as packed:
            packed.extractall(unpack, filter='data')
        source = unpack / 'oci-founder-kit-9.8.7'
        app = self.base / 'app'
        app.mkdir()
        result = subprocess.run([sys.executable, str(source / 'scripts/install.py'), '--project', str(app), '--agent', 'both'], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = json.loads(result.stdout)
        self.assertEqual(installed['kit_version'], '9.8.7')
        self.assertTrue((app / '.agents/skills/example/SKILL.md').is_file())
        self.assertTrue((app / '.claude/skills/example/SKILL.md').is_file())

    def test_diagnostics_do_not_echo_sensitive_errors(self):
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(archive, 'build', side_effect=ValueError('PRIVATE_TEST_SENTINEL')):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                status = archive.main(['--output-dir', str(self.base / 'out')])
        self.assertEqual(status, 2)
        self.assertEqual(output.getvalue(), '')
        self.assertNotIn('PRIVATE_TEST_SENTINEL', errors.getvalue())


class ReleasePublicationBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oci-kit-publish-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.publisher = module('publication_test', ROOT / 'docs/ci/publish_release.py')
        self.names = ['oci-founder-kit-9.8.7.tar.gz', 'release-manifest.json', 'BUILD-METADATA.json', 'SHA256SUMS']
        for name in self.names:
            (self.base / name).write_text('Synthetic public artifact')
        (self.base / 'BUILD-METADATA.json').write_text(json.dumps({'version': '9.8.7', 'archive': self.names[0]}))
        self.environment = {'GITHUB_EVENT_NAME': 'release', 'GH_REPO': 'example/kit', 'GITHUB_SHA': 'a' * 40}

    def main(self):
        with mock.patch.object(sys, 'argv', ['publish_release.py', '--assets', str(self.base), '--tag', 'v9.8.7']):
            self.publisher.main()

    def test_nonrelease_context_refuses_before_network_or_publication(self):
        with mock.patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request'}, clear=True), mock.patch.object(self.publisher, 'run') as run:
            with self.assertRaises(SystemExit):
                self.main()
            run.assert_not_called()

    def test_attestation_failure_prevents_upload(self):
        def run(*args):
            if args[1:3] == ('release', 'view'):
                return json.dumps({'tagName': 'v9.8.7', 'isDraft': False})
            if args[1:3] == ('attestation', 'verify'):
                raise SystemExit('Synthetic verification failure')
            self.fail('Publication reached before attestation acceptance')
        with mock.patch.dict(os.environ, self.environment, clear=True), mock.patch.object(self.publisher, 'run', side_effect=run):
            with self.assertRaises(SystemExit):
                self.main()

    def test_exact_downloaded_bytes_verified_and_upload_never_overwrites(self):
        calls = []
        def run(*args):
            calls.append(args)
            if args[1:3] == ('release', 'view'):
                return json.dumps({'tagName': 'v9.8.7', 'isDraft': False})
            if args[1:3] == ('release', 'download'):
                name = args[args.index('--pattern') + 1]
                destination = Path(args[args.index('--dir') + 1])
                shutil.copyfile(self.base / name, destination / name)
            return ''
        with mock.patch.dict(os.environ, self.environment, clear=True), mock.patch.object(self.publisher, 'run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
            self.main()
        attestations = [row for row in calls if row[1:3] == ('attestation', 'verify')]
        self.assertEqual(len(attestations), 4)
        self.assertTrue(all('--source-digest' in row and '--signer-workflow' in row and '--source-ref' in row for row in attestations))
        upload = [row for row in calls if row[1:3] == ('release', 'upload')]
        self.assertEqual(len(upload), 1)
        self.assertNotIn('--clobber', upload[0])
        self.assertEqual(sum(row[1:3] == ('release', 'download') for row in calls), 4)

    def test_failed_download_identity_does_not_delete_or_replace_assets(self):
        calls = []
        def run(*args):
            calls.append(args)
            if args[1:3] == ('release', 'view'):
                return json.dumps({'tagName': 'v9.8.7', 'isDraft': False})
            if args[1:3] == ('release', 'download'):
                name = args[args.index('--pattern') + 1]
                destination = Path(args[args.index('--dir') + 1])
                (destination / name).write_text('Changed public bytes')
            return ''
        with mock.patch.dict(os.environ, self.environment, clear=True), mock.patch.object(self.publisher, 'run', side_effect=run):
            with self.assertRaises(SystemExit):
                self.main()
        self.assertEqual(sum(row[1:3] == ('release', 'upload') for row in calls), 1)
        self.assertFalse(any('--clobber' in row or 'delete' in row for row in calls))


if __name__ == '__main__':
    unittest.main()
