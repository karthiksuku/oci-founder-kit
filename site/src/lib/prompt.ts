export const repository = 'https://github.com/karthiksuku/oci-founder-kit';

export type Task = 'build' | 'migrate' | 'setup';
export type Agent = 'codex' | 'claude';
export type Stack = 'existing' | 'nextjs' | 'fastapi' | 'choose' | 'taskboard';
export type Selection = { task: Task; agent: Agent; stack: Stack };
export const defaultSelection: Selection = { task: 'build', agent: 'codex', stack: 'existing' };
const anchors = ['', 'main', 'start', 'build', 'migrate', 'setup', 'examples', 'guides', 'evidence'];

// Only public choices are serializable. Never pass a brief through this boundary.
export function normalizeSelection(input: { task?: unknown; agent?: unknown; stack?: unknown }): Selection {
  const task = typeof input.task === 'string' && ['build', 'migrate', 'setup'].includes(input.task) ? input.task as Task : 'build';
  const agent = input.agent === 'claude' ? 'claude' : 'codex';
  const stack = typeof input.stack === 'string' && ['existing', 'nextjs', 'fastapi', 'choose', ...(task === 'build' ? ['taskboard'] : [])].includes(input.stack) ? input.stack as Stack : 'existing';
  return { task, agent, stack };
}

export function readFragment(fragment: string): { anchor: string; selection: Selection } {
  if (fragment.length > 300) return { anchor: 'start', selection: { ...defaultSelection } };
  const [candidate, query = ''] = fragment.replace(/^#/, '').split('?');
  const params = new URLSearchParams(query);
  return {
    anchor: anchors.includes(candidate) ? candidate : 'start',
    selection: normalizeSelection({ task: params.get('task'), agent: params.get('agent'), stack: params.get('stack') }),
  };
}

export function selectionFragment(input: Selection, anchor = 'start'): string {
  const selection = normalizeSelection(input);
  return `#${anchors.includes(anchor) ? anchor : 'start'}?task=${selection.task}&agent=${selection.agent}&stack=${selection.stack}`;
}

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

const stackInstructions: Record<Exclude<Stack, 'taskboard'>, string> = {
  existing: 'Preserve the existing framework, database and identity provider unless I explicitly choose to change them.',
  nextjs: 'For a new application, use Next.js and TypeScript. For an existing app, assess its current stack before recommending changes.',
  fastapi: 'For a new application, use Python and FastAPI. For an existing app, assess its current stack before recommending changes.',
  choose: 'Recommend a small, maintainable stack after reviewing the requirements and any existing code. Explain the tradeoffs.',
};

export function checkpoint(input: Selection): { title: string; results: string[]; guide: string; guideLabel: string } {
  if (input.task === 'migrate') return {
    title: 'A migration assessment you can act on',
    results: ['A dependency inventory, retained services and missing facts.', 'A local validation plan, staging steps and a rollback boundary.'],
    guide: 'docs/MIGRATION-ACCEPTANCE.md', guideLabel: 'Migration acceptance guide',
  };
  if (input.task === 'setup') return {
    title: 'An access plan with clear next actions',
    results: ['Offline readiness results, with denied or unknown checks called out.', 'The administrator steps and scoped compartment/IAM changes to review.'],
    guide: 'docs/START-HERE.md#oci-credentials-and-initial-setup', guideLabel: 'Access and compartment guide',
  };
  if (input.stack === 'taskboard') return {
    title: 'Your own editable Taskboard project',
    results: ['App source in app/, infrastructure in terraform/, and agent skills in your project.', 'With Docker running: add, rename and complete a task locally; record the result.'],
    guide: 'blueprints/fullstack-container/LOCAL.md', guideLabel: 'Local preview requirements',
  };
  return {
    title: 'One useful workflow, running locally',
    results: ['A working app flow you can try, with its local start command.', 'Actual test results and unfinished checks in your project’s progress record.'],
    guide: 'docs/PROJECT-BRIEF.md', guideLabel: 'Define your first workflow',
  };
}

export function createPrompt(input: Selection & { brief: string }): string {
  const task = tasks[input.task];
  const entry = input.agent === 'codex' ? '$oci-kit' : '/oci-kit';
  const taskboard = input.task === 'build' && input.stack === 'taskboard';
  const brief = input.brief.trim().slice(0, 1200);
  const lines = [
    `Read ${repository} and follow its README installation instructions.`,
    'Inspect the project and any existing OCI Founder Kit installation first. If installed, check its status and use its current skills; do not reinstall or overwrite it.',
    ...(taskboard ? [
      `I explicitly choose the editable Node.js/PostgreSQL Taskboard starter. From a kit clone outside my target project, run python3 scripts/blueprint.py create fullstack-container --project /absolute/path/to/my-app --agent ${input.agent}, replacing the example path with my intended project path.`,
      'Use a new folder under an existing parent or an empty existing folder. Refuse any overwrite. If the app already exists, inspect it and continue without regenerating it.',
      'Creation copies files and skills offline; it does not start Docker or deploy anything. Edit the project’s app/ and terraform/ files, not the hidden kit’s reference copy.',
      'From the created project, use python3 local_preview.py start when Docker and Compose are available. Explain missing prerequisites; do not claim the preview ran if it did not.',
    ] : [`If the kit is absent, install into this project for ${input.agent === 'codex' ? 'Codex' : 'Claude Code'}, preserving existing instructions and skills.`]),
    `Then use ${entry}: ${task.goal}`,
  ];
  if (brief) lines.push('', `My project brief: ${brief}`);
  lines.push('');
  if (input.task !== 'setup' && !taskboard) lines.push(stackInstructions[input.stack === 'taskboard' ? 'existing' : input.stack]);
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
    `First checkpoint: ${checkpoint(input).title}.`,
    'Create or update docs/PROGRESS.md in this application using the kit’s progress guide. Preserve existing records; include actual commands/results, unfinished checks and one next action. Keep private evidence outside Git.',
    'Use OCI Well-Architected guidance. Show the exact target, permissions, resources, dated cost estimate and plan before any cloud changes; wait for my approval.',
    'Never ask me to paste private keys, passwords or tokens. Keep credentials, state and private receipts out of chat and Git.',
    'Finish with what was tested, what is still unverified, and the next action.',
  );
  return lines.join('\n');
}

export function resumePrompt(input: Selection): string {
  const entry = input.agent === 'codex' ? '$oci-kit' : '/oci-kit';
  return [
    `Use ${entry} to continue this project’s ${input.task === 'setup' ? 'OCI setup' : input.task === 'migrate' ? 'migration to OCI' : 'local app build and OCI preparation'}.`,
    'Inspect the existing code, project instructions, kit installation status and docs/PROGRESS.md first. Use the installed skills; do not reinstall, regenerate the app or overwrite existing work.',
    ...(input.task !== 'setup' ? [input.stack === 'taskboard'
      ? 'Continue editing this project’s Taskboard app/ and terraform/ files. Keep its Node.js/PostgreSQL stack; do not edit the hidden kit’s reference copy.'
      : stackInstructions[input.stack]] : []),
    'Treat recorded results as evidence to review, not proof of current readiness. If the progress record is missing, reconstruct a short record from the code and actual checks without inventing completed work.',
    'State the first unfinished checkpoint and continue the useful local work. Update the progress record with what was tested, what is still unverified, and the next action.',
    'Use OCI Well-Architected guidance. Past approvals do not authorize new cloud changes. Show the exact current target, permissions, resources, dated costs and plan; wait for my approval before cloud writes.',
    ...(input.task === 'migrate' ? ['Do not change DNS or production data without separate approval.'] : []),
    'Never ask me to paste private keys, passwords or tokens. Keep credentials, state and private receipts out of chat and Git.',
  ].join('\n');
}

export function installCommand(agent: Agent, stack: Stack = 'existing'): string {
  return [
    `git clone ${repository}.git`,
    stack === 'taskboard' ? 'python3 oci-founder-kit/scripts/blueprint.py create fullstack-container \\' : 'python3 oci-founder-kit/scripts/install.py \\',
    `  --project /absolute/path/to/my-app --agent ${agent}`,
    'cd /absolute/path/to/my-app',
  ].join('\n');
}
