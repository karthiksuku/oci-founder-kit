export const stages = {
  idea: {
    title: 'Shape the idea',
    description: 'Start with a person and a problem you can describe clearly.',
    tasks: ['Name the first user', 'Describe one painful task', 'Write a small success test'],
  },
  prototype: {
    title: 'Build a useful prototype',
    description: 'Make one complete flow work before adding more features.',
    tasks: ['Build the smallest useful flow', 'Try it with a potential user', 'Record what needs to change'],
  },
  launch: {
    title: 'Prepare a small launch',
    description: 'Choose the people, checks and support your first release needs.',
    tasks: ['Define release acceptance checks', 'Prepare a recovery plan', 'Invite a small first group'],
  },
};

export function projectName(value) {
  if (value === undefined || value === null || value === '') return 'My project';
  if (typeof value !== 'string' || value.length > 64 || /[\u0000-\u001f\u007f]/.test(value)) return null;
  return value.trim() || 'My project';
}

export function stageInfo(stage) {
  return Object.hasOwn(stages, stage) ? stages[stage] : null;
}
