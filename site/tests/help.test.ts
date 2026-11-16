import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { helpBlocks, section, sourceHelp } from '../src/lib/help.ts';

const read = (path: string) => readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8');
const install = read('docs/INSTALL.md');
const local = read('blueprints/fullstack-container/LOCAL.md');
const start = read('docs/START-HERE.md');

test('inline help comes from current source sections and preserves command bytes', () => {
  const topics = sourceHelp(install, local, start);
  assert.deepEqual(topics.map(topic => topic.id), ['install', 'docker', 'access']);
  const commands = topics[0].blocks.filter(block => block.kind === 'code');
  assert.ok(commands.length > 0);
  for (const block of commands) assert.ok(install.includes(block.text));
  assert.ok(topics[1].blocks.some(block => block.text.includes('Docker must be running')));
  assert.ok(topics[2].blocks.some(block => block.text.includes('private key material')));
  assert.throws(() => section(install, 'Missing source heading'), /Missing help source/);
});

test('help extraction separates prose, lists and code without producing HTML', () => {
  const blocks = helpBlocks('Use **local** checks and [the guide](README.md).\n\n- First\n  continued\n- Second\n\n```sh\npython3 example.py --status\n```');
  assert.deepEqual(blocks, [
    { kind: 'paragraph', text: 'Use local checks and the guide.' },
    { kind: 'list', text: '', items: ['First continued', 'Second'] },
    { kind: 'code', text: 'python3 example.py --status' },
  ]);
  assert.deepEqual(helpBlocks('<script>example</script>'), [{ kind: 'paragraph', text: '<script>example</script>' }]);
});
