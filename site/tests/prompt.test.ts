import assert from 'node:assert/strict';
import test from 'node:test';
import { createPrompt, installCommand, type Agent, type Task } from '../src/lib/prompt.ts';

for (const agent of ['codex', 'claude'] as Agent[]) {
  for (const task of ['build', 'migrate', 'setup'] as Task[]) {
    test(`${agent}/${task} keeps approval and credential boundaries`, () => {
      const prompt = createPrompt({ task, agent, stack: 'existing', brief: 'A project tracker for small teams.' });
      assert.match(prompt, agent === 'codex' ? /\$oci-kit/ : /\/oci-kit/);
      assert.match(prompt, /wait for my approval/);
      assert.match(prompt, /Never ask me to paste private keys, passwords or tokens/);
      assert.match(prompt, /what is still unverified/);
      assert.match(prompt, /A project tracker for small teams\./);
      if (task === 'setup') {
        assert.match(prompt, /offline tool and configuration checks/);
        assert.doesNotMatch(prompt, /Next.js|FastAPI|Preserve the existing framework/);
      } else {
        assert.match(prompt, /Preserve the existing framework, database and identity provider/);
      }
      if (task === 'migrate') assert.match(prompt, /Do not change DNS or production data without separate approval/);
    });
  }
  test(`${agent} install command has a usable multiline command and correct agent`, () => {
    const command = installCommand(agent);
    assert.match(command, /install\.py \\\n  --project/);
    assert.match(command, new RegExp(`--agent ${agent}`));
    assert.doesNotMatch(command, /^\+/m);
  });
}

test('brief is bounded and whitespace-only input produces no empty project section', () => {
  const base = { task: 'build', agent: 'codex', stack: 'choose' } as const;
  assert.doesNotMatch(createPrompt({ ...base, brief: '  \n ' }), /My project brief/);
  const prompt = createPrompt({ ...base, brief: 'x'.repeat(1300) });
  assert.ok(prompt.includes('x'.repeat(1200)));
  assert.ok(!prompt.includes('x'.repeat(1201)));
});

test('a requested new stack does not authorize replacing an existing one', () => {
  for (const stack of ['nextjs', 'fastapi'] as const) {
    const prompt = createPrompt({ task: 'build', agent: 'codex', stack, brief: '' });
    assert.match(prompt, /For an existing app, assess its current stack before recommending changes/);
  }
});
