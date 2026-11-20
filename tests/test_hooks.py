"""Opt-in hook checks exercise staged bytes and host decisions with synthetic data."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('kit_hooks', ROOT / 'scripts/hooks.py')
hooks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hooks)


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=True).stdout


class Staged(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        git(self.root, 'init', '-q')

    def stage(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        git(self.root, 'add', '--', name)
        return path

    def test_staged_bytes_not_clean_worktree_are_scanned(self):
        sentinel = ('ghp_' + 'A' * 30).encode()
        path = self.stage('app.ts', b'export const token = "' + sentinel + b'";')
        path.write_text('safe now')
        result = hooks.scan_staged(self.root)
        self.assertEqual(result['status'], 'blocked')
        self.assertNotIn(sentinel.decode(), json.dumps(result))
        self.assertEqual(result['findings'][0]['path'], 'app.ts')

    def test_unstaged_secret_does_not_change_staged_check(self):
        path = self.stage('app.ts', b'const enabled = true;')
        path.write_text('ghp_' + 'B' * 30)
        self.assertEqual(hooks.scan_staged(self.root)['status'], 'passed')

    def test_replacement_refs_cannot_hide_indexed_secret_bytes(self):
        sentinel = ('ghp_' + 'R' * 30).encode()
        self.stage('app.ts', sentinel)
        original = git(self.root, 'rev-parse', ':app.ts').decode().strip()
        (self.root / 'clean.txt').write_text('const enabled = true;')
        replacement = git(self.root, 'hash-object', '-w', 'clean.txt').decode().strip()
        git(self.root, 'replace', original, replacement)
        self.assertEqual(git(self.root, '--no-replace-objects', 'cat-file', 'blob', original), sentinel)
        for public in (False, True):
            with self.subTest(public=public):
                result = hooks.scan_staged(self.root, public=public, all_tracked=public)
                self.assertEqual(result['status'], 'blocked')
                self.assertEqual(result['findings'], [{'path': 'app.ts', 'rule': 'github-token'}])
                self.assertEqual(result['incomplete'], [])
                self.assertNotIn(sentinel.decode(), json.dumps(result))

    def test_private_files_and_binary_blobs_are_checked(self):
        self.stage('private.auto.tfvars.json', b'{}')
        self.stage('backend.tfbackend', b'private')
        self.stage('backend.tfbackend.json', b'{}')
        self.stage('blob.bin', b'\0prefix' + ('ghp_' + 'C' * 30).encode())
        result = hooks.scan_staged(self.root)
        self.assertEqual({x['path'] for x in result['findings']}, {'private.auto.tfvars.json', 'backend.tfbackend', 'backend.tfbackend.json', 'blob.bin'})

    def test_example_suffix_is_not_a_secret_bypass(self):
        self.stage('.env.example', b'ACCESS_TOKEN="' + ('ghp_' + 'D' * 30).encode() + b'"')
        self.assertEqual(hooks.scan_staged(self.root)['status'], 'blocked')

    def test_local_preview_private_settings_are_blocked_even_without_a_token_pattern(self):
        self.stage('blueprints/fullstack-container/.local-preview/settings.json', b'{}')
        result = hooks.scan_staged(self.root)
        self.assertEqual(result['status'], 'blocked')

    def test_placeholder_examples_are_allowed(self):
        self.stage('.env.example', b'DATABASE_URL=<set-locally>\nAPI_' + b'KEY="${API_KEY}"\n')
        self.stage('terraform.tfvars.example', b'region = "<your-region>"\n')
        self.assertEqual(hooks.scan_staged(self.root)['status'], 'passed')

    def test_sensitive_config_backup_and_log_paths_block_without_content_matches(self):
        names = ['.npmrc', '.pypirc', '.git-credentials', '.netrc', '.npmrc.backup',
                 '.docker/config.json', '.aws/config', '.ssh/config', '.azure/accessTokens.json',
                 '.oci-kit/state.json', '.OcI-KiT/evidence/runtime.json', '.oci-kit/updates/journal.json',
                 '.kube/config', 'runtime.tfvars.backup', 'runtime.tfvars.json.bak', 'runtime.tfvars~',
                 'runtime.tfbackend.backup', 'runtime.tfbackend.json.old', 'runtime.tfstate.backup',
                 'runtime.tfstate~', 'diagnostic.log', 'diagnostic.log.1', 'diagnostic.log.gz', 'diagnostic.log~',
                 '.ENV', '.ENV.LOCAL', 'KEY.PEM', 'KEY.PFX', 'TFPLAN.PRIVATE', '.DOCKER/config.json',
                 '.NPMRC', 'RUNTIME.TFVARS.BACKUP', '.DoCkEr/config.json', '.AwS/config', '.SsH/config',
                 '.AzUrE/accessTokens.json', '.KuBe/config', '.NeTrC', '.PyPiRc', '.GiT-CrEdEnTiAlS',
                 'runtime.TfBaCkEnD.JsOn.OlD', 'diagnostic.LoG.1', 'key.PeM',
                 '.env.production.example', '.EnV.PrOdUcTiOn.ExAmPlE',
                 'private-env/.env.example/runtime-config.json', 'private-env/.EnV.ExAmPlE/nested.json',
                 'private-env/.env/config.example', 'private-env/.env.production.example/config.example']
        for name in names:
            self.stage('nested/' + name, b'synthetic diagnostic data without credential patterns')
        result = hooks.scan_staged(self.root, public=True)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual({item['path'] for item in result['findings']}, {'nested/' + name for name in names})
        self.assertEqual({item['rule'] for item in result['findings']}, {'private-artifact'})

    def test_config_backup_and_log_examples_still_receive_content_checks(self):
        for name in ['.npmrc.example', '.pypirc.example', '.git-credentials.example', '.netrc.example',
                     'backend.tfbackend.json.example', 'state.tfstate.example', 'diagnostic.log.example',
                     '.ENV.example', 'RUNTIME.TFVARS.EXAMPLE']:
            self.stage(name, b'<set-locally>\n')
        self.assertEqual(hooks.scan_staged(self.root, public=True)['status'], 'passed')
        self.stage('.npmrc.example', ('ghp_' + 'Q' * 30).encode())
        result = hooks.scan_staged(self.root, public=True)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['findings'], [{'path': '.npmrc.example', 'rule': 'github-token'}])

    def test_provider_identifiers_are_not_partial_api_tokens(self):
        self.stage('types.json', json.dumps([
            'aws_msk_scram_secret_association',
            'google_compute_disk_resource_policy_attachment',
        ]).encode())
        self.assertEqual(hooks.scan_staged(self.root)['status'], 'passed')

    def test_delimited_api_tokens_still_block_without_echo(self):
        for prefix in ('sk-', 'sk_', 'xai-'):
            sentinel = (prefix + 'A' * 32).encode()
            for separator in (b'', b'=', b'"', b' ', b'\x00'):
                rules = hooks.content_rules(separator + sentinel)
                self.assertIn('api-token', rules)
                self.assertNotIn(sentinel.decode(), json.dumps(rules))

    def test_paths_with_newlines_are_data_not_instructions(self):
        name = 'strange\nname.ts'
        self.stage(name, ('ghp_' + 'E' * 30).encode())
        result = hooks.scan_staged(self.root)
        self.assertEqual(result['findings'][0]['path'], name)
        self.assertNotIn('\nname', hooks.finding_summary(result))

    def test_limits_fail_incomplete_without_reading_large_blob(self):
        self.stage('large.dat', b'x' * 1025)
        with mock.patch.object(hooks, 'MAX_BLOB', 1024):
            self.assertEqual(hooks.scan_staged(self.root)['status'], 'incomplete')

    def test_symlink_blob_is_not_dereferenced(self):
        if os.name == 'nt': self.skipTest('symlink fixture')
        outside = self.root / 'outside'
        outside.write_text('ghp_' + 'F' * 30)
        (self.root / 'link.txt').symlink_to(outside)
        git(self.root, 'add', '--', 'link.txt')
        self.assertEqual(hooks.scan_staged(self.root)['status'], 'passed')

    def test_deleted_secret_file_is_not_read(self):
        self.stage('.env', b'private')
        git(self.root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
        git(self.root, 'rm', '-q', '--', '.env')
        self.assertEqual(hooks.scan_staged(self.root)['status'], 'passed')

    def test_staged_scan_does_not_execute_repository_fsmonitor(self):
        self.stage('app.py', b'value = 1\n')
        helper = self.root / 'fake-fsmonitor'
        marker = self.root / 'monitor-ran'
        helper.write_text(f'#!{sys.executable}\nfrom pathlib import Path\n'
                          'Path(__file__).with_name("monitor-ran").write_text("synthetic")\n'
                          'print("token\\0", end="")\n')
        helper.chmod(0o700)
        git(self.root, 'config', 'core.fsmonitor', str(helper))
        self.assertFalse(marker.exists())
        result = hooks.scan_staged(self.root)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['checked'], 1)
        self.assertFalse(marker.exists(), 'Read-only scan invoked repository code')

    def test_missing_promisor_blob_is_incomplete_without_remote_helper_execution(self):
        self.stage('app.py', b'value = 1\n')
        oid = git(self.root, 'rev-parse', ':app.py').decode().strip()
        (self.root / '.git/objects' / oid[:2] / oid[2:]).unlink()
        helper = self.root / 'fake-remote-helper'
        marker = self.root / 'remote-helper-ran'
        helper.write_text(f'#!{sys.executable}\nfrom pathlib import Path\nimport sys\n'
                          'Path(__file__).with_name("remote-helper-ran").write_text("synthetic")\n'
                          'sys.exit(1)\n')
        helper.chmod(0o700)
        for key, value in [('core.repositoryformatversion', '1'), ('extensions.partialClone', 'origin'),
                           ('remote.origin.url', 'ext::' + str(helper)), ('remote.origin.promisor', 'true'),
                           ('remote.origin.partialclonefilter', 'blob:none'), ('protocol.ext.allow', 'always')]:
            git(self.root, 'config', key, value)
        self.assertFalse(marker.exists())
        result = hooks.scan_staged(self.root)
        self.assertEqual(result['status'], 'incomplete')
        self.assertFalse(marker.exists(), 'Offline scan invoked a promisor remote helper')


class Guard(unittest.TestCase):
    def test_cloud_mutations_are_caught_with_wrappers_and_options(self):
        for command in ['terraform apply plan', '/usr/bin/terraform -chdir=infra destroy',
                        'env FOO=x tofu apply x', 'bash -c "oci iam compartment create --name demo"',
                        'oci os bucket delete --bucket-name example', 'oci raw-request --http-method POST --target-uri x',
                        'docker push registry.example/image', 'kubectl apply -f app.yaml']:
            self.assertIsNotNone(hooks.cloud_reason(command), command)

    def test_read_commands_and_gate_are_not_auto_approved_or_blocked(self):
        for command in ['terraform show -json plan', 'oci iam compartment list',
                        'oci os bucket get --bucket-name demo', 'python3 .oci-founder-kit/skills/oci-deploy/scripts/deploy_gate.py apply --help',
                        'printf "terraform apply"', 'git status --short']:
            self.assertIsNone(hooks.cloud_reason(command), command)

    def test_init_and_plan_need_backend_review_including_wrapped_calls(self):
        for command in ['terraform init', 'terraform plan -out=tfplan',
                        'terraform -chdir=infra plan', 'env FOO=x tofu -chdir infra init',
                        'bash -c "terraform init -backend-config=private.tfbackend.json"']:
            self.assertIsNotNone(hooks.cloud_reason(command), command)
        for command in ['terraform plan -help', 'terraform init --help',
                        'terraform -chdir=infra show -json plan', 'terraform fmt -check']:
            self.assertIsNone(hooks.cloud_reason(command), command)

    def test_shell_substitution_is_inspected(self):
        self.assertIsNotNone(hooks.cloud_reason('echo $(terraform destroy)'))
        self.assertIsNotNone(hooks.cloud_reason('terraform\\\n apply'))

    def test_skopeo_remote_writes_need_review_but_local_preparation_and_reads_do_not(self):
        for command in [
            'skopeo copy --preserve-digests dir:prepared docker://registry.example/app@sha256:abc',
            'skopeo copy docker://registry.example/source docker://registry.example/destination --retry-times 0',
            'skopeo delete docker://registry.example/app:old',
        ]:
            self.assertIsNotNone(hooks.cloud_reason(command), command)
        for command in [
            'skopeo copy docker-archive:local.tar dir:prepared',
            'skopeo copy docker://registry.example/app dir:downloaded',
            'skopeo inspect docker://registry.example/app',
        ]:
            self.assertIsNone(hooks.cloud_reason(command), command)

    def test_malformed_command_does_not_echo_secrets(self):
        sentinel = 'ghp_' + 'G' * 30
        reason = hooks.cloud_reason('terraform apply "' + sentinel)
        self.assertIsNotNone(reason)
        self.assertNotIn(sentinel, reason)

    def test_deny_shape_has_no_allow(self):
        for host in ('claude', 'codex'):
            result = hooks.respond(host, 'PreToolUse', 'Use reviewed plan', deny=True)
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
            self.assertNotIn('allow', json.dumps(result))

    def test_commit_with_in_command_staging_is_not_claimed_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, 'init', '-q')
            result = hooks.handle_event(root, 'codex', 'PreToolUse', {
                'hook_event_name': 'PreToolUse', 'cwd': str(root), 'tool_name': 'Bash',
                'tool_input': {'command': 'git add . && git commit -m change'}}, {'secrets'})
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
            self.assertIn('separately', result['hookSpecificOutput']['permissionDecisionReason'])

    def test_stop_is_nonblocking_and_transcript_is_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {'hook_event_name': 'Stop', 'cwd': tmp, 'transcript_path': '/never/read/this', 'stop_hook_active': True}
            result = hooks.handle_event(Path(tmp), 'codex', 'Stop', payload, {'handoff'})
            self.assertNotIn('decision', result)
            self.assertNotIn('continue', result)


class Validation(unittest.TestCase):
    def test_only_data_is_parsed_no_project_script_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'app.py').write_text('raise RuntimeError("must never run")\n')
            (root / 'bad.json').write_text('{invalid')
            result = hooks.validate_paths(root, ['app.py', 'bad.json'])
            self.assertEqual(result['checked'], 2)
            self.assertEqual(result['findings'], [{'path': 'bad.json', 'rule': 'invalid-json'}])

    def test_symlink_and_outside_paths_are_not_opened(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'link.json').symlink_to('/not/a/project/file')
            result = hooks.validate_paths(root, ['../private.json', 'link.json'])
            self.assertEqual(result['checked'], 0)
            self.assertEqual(result['skipped'], 2)

    def test_json_errors_do_not_include_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sentinel = 'ghp_' + 'H' * 30
            (root / 'bad.json').write_text('{' + sentinel)
            self.assertNotIn(sentinel, json.dumps(hooks.validate_paths(root, ['bad.json'])))

    def test_validation_findings_redact_tokens_in_paths_and_event_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.hooks').mkdir()
            sentinel = 'ghp_' + 'R' * 30
            folder = root / ('sample-' + sentinel)
            folder.mkdir()
            for name, content in [('bad.json', '{invalid'), ('bad.py', 'def broken('),
                                  ('bad.toml', 'x = ['), ('SKILL.md', 'no frontmatter')]:
                path = folder / name
                path.write_text(content)
                with self.subTest(name=name), mock.patch.object(hooks, 'ROOT', root):
                    result = hooks.validate_paths(root, [str(path)])
                    self.assertEqual(len(result['findings']), 1)
                    self.assertNotIn(sentinel, json.dumps(result))
                    self.assertIn('<redacted>', result['findings'][0]['path'])
                    event = hooks.handle_event(root, 'codex', 'PostToolUse', {
                        'hook_event_name': 'PostToolUse', 'tool_name': 'Write',
                        'tool_input': {'file_path': str(path)}}, {'validation'})
                    self.assertIn('Offline syntax check', json.dumps(event))
                    self.assertNotIn(sentinel, json.dumps(event))
                    self.assertNotIn(sentinel, (root / '.hooks/validation-cache.json').read_text())

    def test_readiness_does_not_read_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = hooks.readiness(Path(tmp))
            self.assertIn('Local', result)
            self.assertNotIn('credentials verified', result.lower())


class PublicationAndAdapters(unittest.TestCase):
    def test_public_checks_are_separate_from_normal_secret_rules(self):
        text = ('https://private.' + 'oraclecorp' + '.com/path').encode()
        self.assertEqual(hooks.content_rules(text), [])
        self.assertIn('private-workplace-url', hooks.public_rules(text))
        self.assertIn('local-home-path', hooks.public_rules(('/home/' + 'person/project/').encode()))
        self.assertEqual(hooks.public_rules(b'https://docs.oracle.com/en-us/iaas/'), [])

    def test_public_mode_scans_already_committed_index_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, 'init', '-q')
            (root / 'notes.md').write_text('https://workspace.' + 'enterprise.slack' + '.com/archives/example')
            git(root, 'add', 'notes.md')
            git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
            self.assertEqual(hooks.scan_staged(root)['status'], 'passed')
            result = hooks.scan_staged(root, public=True, all_tracked=True)
            self.assertEqual(result['findings'], [{'path': 'notes.md', 'rule': 'private-workplace-url'}])

    def test_commit_paths_or_alternate_indexes_need_separate_staging(self):
        for command in ['git commit app.py', 'git commit -am change',
                        'git -C elsewhere commit -m x', 'env GIT_INDEX_FILE=other git commit -m x',
                        'bash -lc "git commit -m x"']:
            self.assertEqual(hooks._commit_command(command), (True, False), command)
        self.assertEqual(hooks._commit_command('git commit -m "some changes"'), (True, True))
        self.assertEqual(hooks._commit_command('printf "git commit"'), (False, False))

    def test_oci_values_are_not_misread_as_read_verbs(self):
        self.assertIsNotNone(hooks.cloud_reason('oci compute volume-attachment attach --display-name list'))
        self.assertIsNone(hooks.cloud_reason('oci --profile local os bucket get --name create'))
        self.assertIsNotNone(hooks.cloud_reason('bash -lc "terraform apply plan"'))
        self.assertIsNone(hooks.cloud_reason('echo $()'))

    def test_invalid_event_and_stale_script_produce_explicit_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            for host in ('claude', 'codex'):
                command = [sys.executable, str(ROOT / 'scripts/hooks.py'), 'event', '--host', host,
                           '--event', 'PreToolUse', '--project', tmp]
                for data, extra in [('not json', []), ('{}', ['--expected-sha256', '0' * 64])]:
                    run = subprocess.run(command + extra, input=data, text=True, capture_output=True)
                    self.assertEqual(run.returncode, 0)
                    result = json.loads(run.stdout)
                    self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_both_adapter_commands_receive_and_deny_real_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {'hook_event_name': 'PreToolUse', 'cwd': tmp, 'tool_name': 'Bash',
                       'tool_input': {'command': 'terraform apply plan'}}
            for host in ('claude', 'codex'):
                run = subprocess.run([sys.executable, str(ROOT / 'scripts/hooks.py'), 'event', '--host', host,
                                      '--event', 'PreToolUse', '--project', tmp],
                                     input=json.dumps(payload), text=True, capture_output=True)
                self.assertEqual(run.returncode, 0)
                self.assertEqual(json.loads(run.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')
                self.assertEqual(run.stderr, '')

    def test_advisory_validation_debounces_without_recording_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.hooks').mkdir()
            cache = root / '.hooks/cache.json'
            (root / 'app.py').write_text('x = 1')
            with mock.patch.object(hooks, 'ROOT', root):
                first = hooks.validate_paths(root, ['app.py'], cache_path=cache)
                second = hooks.validate_paths(root, ['app.py'], cache_path=cache)
            self.assertEqual(first['checked'], 1)
            self.assertEqual(second['checked'], 0)
            self.assertNotIn('app.py', cache.read_text())
            self.assertNotIn('x = 1', cache.read_text())

    def test_missing_tool_input_denies_pretool_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = hooks.handle_event(Path(tmp), 'claude', 'PreToolUse', {'hook_event_name': 'PreToolUse'}, {'cloud'})
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')


    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO safety')
    def test_named_pipe_source_is_skipped_without_open_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.mkfifo(root / 'app.json')
            result = hooks.validate_paths(root, ['app.json'])
            self.assertEqual(result['checked'], 0)
            self.assertEqual(result['skipped'], 1)


    def test_filename_tokens_are_redacted_in_reports(self):
        token = 'ghp_' + 'J' * 30
        self.assertNotIn(token, hooks.display_path('prefix-' + token + '.txt'))


if __name__ == '__main__': unittest.main()
