export const repository = 'https://github.com/karthiksuku/oci-founder-kit';

export type Task = 'build' | 'migrate' | 'setup';
export type Agent = 'codex' | 'claude';
export type Stack = 'existing' | 'nextjs' | 'fastapi' | 'choose';

export const tasks = {
  build: {
    label: 'Build an app',
    goal: 'Build my application on OCI, starting with a working local version.',
    next: 'Open an empty project folder or your existing app in your coding agent. Paste this prompt to define the first working version.',
    example: 'A customer portal where clients can track projects, share files and leave feedback.',
  },
  migrate: {
    label: 'Migrate an app',
    goal: 'Migrate this existing application from Vercel or Netlify to OCI, starting with a read-only repository assessment.',
    next: 'Open your existing application repository in your coding agent. Paste this prompt to assess compatibility before changing anything.',
    example: 'Move my Next.js app from Vercel. Keep the existing database, sign-in and payments.',
  },
  setup: {
    label: 'Set up OCI',
    goal: 'Check my OCI readiness and prepare a dedicated compartment and scoped access plan.',
    next: 'Open a project folder in your coding agent. Paste this prompt for local readiness checks and a guided account setup plan.',
    example: 'Prepare a separate development environment for my startup with scoped access and cost alerts.',
  },
} satisfies Record<Task, { label: string; goal: string; next: string; example: string }>;

const stackInstructions: Record<Stack, string> = {
  existing: 'Preserve the existing framework, database and identity provider unless I explicitly choose to change them.',
  nextjs: 'For a new application, use Next.js and TypeScript. For an existing app, assess its current stack before recommending changes.',
  fastapi: 'For a new application, use Python and FastAPI. For an existing app, assess its current stack before recommending changes.',
  choose: 'Recommend a small, maintainable stack after reviewing the requirements and any existing code. Explain the tradeoffs.',
};

export function createPrompt(input: { task: Task; agent: Agent; stack: Stack; brief: string }): string {
  const task = tasks[input.task];
  const entry = input.agent === 'codex' ? '$oci-kit' : '/oci-kit';
  const brief = input.brief.trim().slice(0, 1200);
  const lines = [
    `Read ${repository} and follow its README installation instructions.`,
    `Install into this project for ${input.agent === 'codex' ? 'Codex' : 'Claude Code'}, preserving existing instructions and skills.`,
    `Then use ${entry}: ${task.goal}`,
  ];
  if (brief) lines.push('', `My project brief: ${brief}`);
  lines.push('');
  if (input.task !== 'setup') lines.push(stackInstructions[input.stack]);
  if (input.task === 'build') {
    lines.push('Agree the smallest useful app, implement it, and run meaningful local tests. Include responsive layouts and clear empty, loading and error states.');
    lines.push('Keep local development moving while OCI setup is incomplete.');
  } else if (input.task === 'migrate') {
    lines.push('Inventory provider-specific features and environment variable names without exposing values. Preserve source behavior, data, identity and integrations.');
    lines.push('Adapt and test locally, then prepare staging, data validation, traffic cutover and rollback steps. Do not change DNS or production data without separate approval.');
  } else {
    lines.push('Start with offline tool and configuration checks. Guide account enrollment and administrator-only steps when needed.');
    lines.push('Use an explicitly selected existing parent compartment and group. Prepare least-privilege IAM and cost-alert guidance.');
  }
  lines.push(
    'Use OCI Well-Architected guidance. Show the exact target, permissions, resources, dated cost estimate and plan before any cloud changes; wait for my approval.',
    'Never ask me to paste private keys, passwords or tokens. Keep credentials, state and private receipts out of chat and Git.',
    'Finish with what was tested, what is still unverified, and the next action.',
  );
  return lines.join('\n');
}

export function installCommand(agent: Agent): string {
  return [
    `git clone ${repository}.git`,
    'python3 oci-founder-kit/scripts/install.py \\',
    `  --project /absolute/path/to/my-app --agent ${agent}`,
    'cd /absolute/path/to/my-app',
  ].join('\n');
}
