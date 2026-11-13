"""Project-local hook settings preserve existing entries and uninstall precisely."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('hooks_install', ROOT / 'scripts/hooks_install.py')
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class HookInstallation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='founder hooks ')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        scripts = self.project / '.oci-founder-kit/scripts'
        scripts.mkdir(parents=True)
        shutil.copyfile(ROOT / 'scripts/hooks.py', scripts / 'hooks.py')

    def config(self, host, value):
        path = self.project / installer.CONFIG[host]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def test_dry_run_does_not_write_config_or_metadata(self):
        result = installer.install(self.project, 'both', dry_run=True)
        self.assertEqual(result['agents'], ['claude', 'codex'])
        self.assertFalse((self.project / '.claude').exists())
        self.assertFalse((self.project / '.oci-founder-kit/.hooks').exists())

    def test_preserves_settings_and_unrelated_hooks(self):
        existing = {'env': {'KEEP': 'same'}, 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo existing'}]}]}}
        path = self.config('claude', existing)
        installer.install(self.project, 'claude')
        after = json.loads(path.read_text())
        self.assertEqual(after['env'], existing['env'])
        self.assertEqual(after['hooks']['Stop'][0], existing['hooks']['Stop'][0])
        self.assertEqual(len(after['hooks']['Stop']), 2)
        installer.uninstall(self.project, 'claude')
        self.assertEqual(json.loads(path.read_text()), existing)

    def test_uninstall_preserves_new_user_hooks_and_settings(self):
        installer.install(self.project, 'codex')
        path = self.project / installer.CONFIG['codex']
        after = json.loads(path.read_text())
        extra = {'hooks': [{'type': 'command', 'command': 'echo later'}]}
        after['hooks']['Stop'].append(extra)
        after['description'] = 'My hooks'
        path.write_text(json.dumps(after))
        installer.uninstall(self.project, 'codex')
        self.assertEqual(json.loads(path.read_text()), {'description': 'My hooks', 'hooks': {'Stop': [extra]}})

    def test_changed_owned_entry_refuses_uninstall(self):
        installer.install(self.project, 'codex')
        path = self.project / installer.CONFIG['codex']
        after = json.loads(path.read_text())
        after['hooks']['Stop'][0]['hooks'][0]['command'] += ' --changed'
        path.write_text(json.dumps(after))
        before = path.read_bytes()
        with self.assertRaises(ValueError): installer.uninstall(self.project, 'codex')
        self.assertEqual(path.read_bytes(), before)

    def test_second_install_refuses_and_leaves_config_identical(self):
        installer.install(self.project, 'claude')
        path = self.project / installer.CONFIG['claude']
        before = path.read_bytes()
        with self.assertRaises(ValueError): installer.install(self.project, 'claude')
        self.assertEqual(path.read_bytes(), before)

    def test_malformed_or_duplicate_config_refuses_all_before_writes(self):
        path = self.config('codex', {})
        for value in ('[]', '{bad', '{"hooks":{},"hooks":{}}', '{"hooks":{"Stop":"bad"}}'):
            path.write_text(value)
            with self.assertRaises(ValueError): installer.install(self.project, 'both')
            self.assertEqual(path.read_text(), value)
            self.assertFalse((self.project / '.claude').exists())

    def test_symlink_directory_or_file_refuses(self):
        if os.name == 'nt': self.skipTest('symlinks')
        with tempfile.TemporaryDirectory() as outside:
            (self.project / '.codex').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): installer.install(self.project, 'both')
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_no_global_settings_or_trust_are_generated(self):
        result = installer.install(self.project, 'both')
        self.assertTrue(result['trust_review_required'])
        for host in ('claude', 'codex'):
            data = (self.project / installer.CONFIG[host]).read_text()
            self.assertNotIn('bypass', data)
            self.assertNotIn('trusted', data)
            self.assertNotIn('PermissionRequest', data)
            self.assertIn('--expected-sha256', data)
        self.assertFalse((self.project / '.codex/config.toml').exists())

    def test_clean_uninstall_removes_new_empty_configuration(self):
        installer.install(self.project, 'both')
        installer.uninstall(self.project, 'both')
        for host in ('claude', 'codex'):
            self.assertFalse((self.project / installer.CONFIG[host]).exists())

    def test_status_detects_script_change(self):
        installer.install(self.project, 'codex')
        script = self.project / '.oci-founder-kit/scripts/hooks.py'
        script.write_text(script.read_text() + '\n# changed\n')
        result = installer.status(self.project, 'codex')
        self.assertEqual(result['agents'][0]['status'], 'script-changed')

    def test_check_selection_installs_only_relevant_events(self):
        installer.install(self.project, 'claude', checks={'secrets'})
        data = json.loads((self.project / installer.CONFIG['claude']).read_text())
        self.assertEqual(set(data['hooks']), {'PreToolUse'})


    def test_tampered_registration_cannot_remove_an_unrelated_hook(self):
        extra = {'hooks': [{'type': 'command', 'command': 'echo existing'}]}
        path = self.config('claude', {'hooks': {'Stop': [extra]}})
        installer.install(self.project, 'claude')
        record = self.project / '.oci-founder-kit/.hooks/claude.json'
        registration = json.loads(record.read_text())
        registration['owned'] = {'Stop': [extra]}
        record.write_text(json.dumps(registration))
        before = path.read_bytes()
        with self.assertRaises(ValueError): installer.uninstall(self.project, 'claude')
        self.assertEqual(before, path.read_bytes())

    def test_partial_write_failure_rolls_back_completed_writes(self):
        path = self.config('claude', {'env': {'KEEP': 'same'}})
        before = path.read_bytes()
        real = installer.replace_file
        def failing(path, project, old, new):
            if path.name == 'hooks.json': raise OSError('simulated')
            return real(path, project, old, new)
        with mock.patch.object(installer, 'replace_file', side_effect=failing):
            with self.assertRaises(OSError): installer.install(self.project, 'both')
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.project / '.oci-founder-kit/.hooks/claude.json').exists())

    def test_modified_user_settings_survive_uninstall_dry_run(self):
        installer.install(self.project, 'claude')
        path = self.project / installer.CONFIG['claude']
        before = path.read_bytes()
        installer.uninstall(self.project, 'claude', dry_run=True)
        self.assertEqual(path.read_bytes(), before)

    def test_commands_quote_paths_with_spaces(self):
        import shlex
        installer.install(self.project, 'codex')
        config = json.loads((self.project / installer.CONFIG['codex']).read_text())
        command = config['hooks']['SessionStart'][0]['hooks'][0]['command']
        args = shlex.split(command)
        self.assertEqual(args[args.index('--project') + 1], str(self.project))
        self.assertTrue(Path(args[1]).is_file())


    def test_installed_commands_execute_with_spaces_and_validate_digest(self):
        installer.install(self.project, 'both')
        payload = json.dumps({'hook_event_name': 'PreToolUse', 'cwd': str(self.project),
                              'tool_name': 'Bash', 'tool_input': {'command': 'terraform apply plan'}})
        for host in ('claude', 'codex'):
            data = json.loads((self.project / installer.CONFIG[host]).read_text())
            command = data['hooks']['PreToolUse'][0]['hooks'][0]['command']
            run = subprocess.run(command, shell=True, cwd=self.project, input=payload,
                                 text=True, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, 0)
            response = json.loads(run.stdout)
            self.assertEqual(response['hookSpecificOutput']['permissionDecision'], 'deny')
            self.assertIn('Direct cloud mutation', response['hookSpecificOutput']['permissionDecisionReason'])
        script = self.project / '.oci-founder-kit/scripts/hooks.py'
        script.write_text(script.read_text() + '\n# reviewed update required\n')
        run = subprocess.run(command, shell=True, cwd=self.project, input=payload,
                             text=True, capture_output=True, timeout=10)
        self.assertEqual(json.loads(run.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertIn('could not complete', run.stdout)


    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO safety')
    def test_named_pipe_settings_refused_without_open_block(self):
        parent = self.project / '.codex'
        parent.mkdir()
        os.mkfifo(parent / 'hooks.json')
        with self.assertRaises(ValueError): installer.install(self.project, 'codex')


if __name__ == '__main__': unittest.main()
