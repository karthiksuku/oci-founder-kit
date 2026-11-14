import assert from 'node:assert/strict';
import test from 'node:test';
import { checkpoint, createPrompt, defaultSelection, installCommand, normalizeSelection, readFragment, resumePrompt, selectionFragment, type Agent, type Task } from '../src/lib/prompt.ts';

for (const agent of ['codex', 'claude'] as Agent[]) {
  for (const task of ['build', 'migrate', 'setup'] as Task[]) {
    test(`${agent}/${task} keeps approval and credential boundaries`, () => {
      const prompt = createPrompt({ task, agent, stack: 'existing', brief: 'A project tracker for small teams.' });
      assert.match(prompt, agent === 'codex' ? /\$oci-kit/ : /\/oci-kit/);
      assert.match(prompt, /wait for my approval/);
      assert.match(prompt, /Never ask me to paste private keys, passwords or tokens/);
      assert.match(prompt, /what is still unverified/);
      assert.match(prompt, /If installed, check its status/);
      assert.match(prompt, /do not reinstall or overwrite/);
      assert.match(prompt, /docs\/PROGRESS.md/);
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

test('Taskboard creation is explicit, editable, offline and separate from the Docker preview', () => {
  for (const agent of ['codex', 'claude'] as Agent[]) {
    const chosen = { task: 'build', agent, stack: 'taskboard' } as const;
    const prompt = createPrompt({ ...chosen, brief: '' });
    assert.match(prompt, /blueprint.py create fullstack-container/);
    assert.ok(prompt.includes(`--agent ${agent}`));
    assert.match(prompt, /new folder under an existing parent or an empty existing folder/);
    assert.match(prompt, /Refuse any overwrite/);
    assert.match(prompt, /copies files and skills offline/);
    assert.match(prompt, /project’s app\/ and terraform\//);
    assert.match(prompt, /python3 local_preview.py start when Docker and Compose are available/);
    assert.match(checkpoint(chosen).title, /editable Taskboard/);
    assert.match(installCommand(agent, 'taskboard'), /blueprint.py create fullstack-container \\\n  --project/);
    assert.doesNotMatch(installCommand(agent, 'taskboard'), /local_preview|install.py/);
  }
  for (const stack of ['existing', 'nextjs', 'fastapi', 'choose'] as const) {
    const prompt = createPrompt({ task: 'build', agent: 'codex', stack, brief: '' });
    assert.doesNotMatch(prompt, /Taskboard|blueprint.py create|Node.js\/PostgreSQL/);
  }
});

test('resume prompts inspect existing evidence, preserve choices and require current approvals', () => {
  for (const agent of ['codex', 'claude'] as Agent[]) {
    for (const task of ['build', 'migrate', 'setup'] as Task[]) {
      const result = resumePrompt({ task, agent, stack: 'existing' });
      assert.match(result, agent === 'codex' ? /\$oci-kit/ : /\/oci-kit/);
      assert.match(result, /docs\/PROGRESS.md/);
      assert.match(result, /do not reinstall, regenerate the app or overwrite/);
      assert.match(result, /without inventing completed work/);
      assert.match(result, /Past approvals do not authorize new cloud changes/);
      assert.match(result, /wait for my approval/);
      if (task === 'migrate') assert.match(result, /Do not change DNS or production data/);
      if (task === 'setup') assert.doesNotMatch(result, /framework|Taskboard/);
    }
  }
  assert.match(resumePrompt({ task: 'build', agent: 'claude', stack: 'nextjs' }), /Next.js and TypeScript/);
  assert.match(resumePrompt({ task: 'build', agent: 'claude', stack: 'fastapi' }), /Python and FastAPI/);
  assert.match(resumePrompt({ task: 'build', agent: 'codex', stack: 'taskboard' }), /project’s Taskboard app\/ and terraform\//);
});

test('fragments round-trip only public choices and preserve supported anchors', () => {
  for (const task of ['build', 'migrate', 'setup'] as Task[]) {
    for (const agent of ['codex', 'claude'] as Agent[]) {
      const chosen = { task, agent, stack: 'fastapi' } as const;
      for (const anchor of ['', 'start', 'guides', 'examples', 'main']) {
        assert.deepEqual(readFragment(selectionFragment(chosen, anchor)), { anchor, selection: chosen });
      }
    }
  }
  const input = { ...defaultSelection, brief: 'must-not-persist', unknown: 'extra' };
  assert.equal(selectionFragment(input), '#start?task=build&agent=codex&stack=existing');
  assert.deepEqual(readFragment('#guides'), { anchor: 'guides', selection: defaultSelection });
  assert.deepEqual(readFragment('#start?task=invalid&agent=unknown&stack=%3Cscript%3E').selection, defaultSelection);
  assert.deepEqual(readFragment('#' + 'x'.repeat(301)), { anchor: 'start', selection: defaultSelection });
  assert.equal(readFragment('#unknown?task=migrate').anchor, 'start');
  assert.equal(normalizeSelection({ task: 'migrate', agent: 'claude', stack: 'taskboard' }).stack, 'existing');
  assert.equal(normalizeSelection({ task: 'setup', stack: 'taskboard' }).stack, 'existing');
  const privateInput = readFragment('#start?task=migrate&brief=private&token=private');
  assert.equal(selectionFragment(privateInput.selection, privateInput.anchor), '#start?task=migrate&agent=codex&stack=existing');
});

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
