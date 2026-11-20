export const repository = 'https://github.com/karthiksuku/oci-founder-kit';

// A side-by-side Pages preview must install and document the same revision.
const previewRevision = import.meta.env?.PUBLIC_KIT_PREVIEW_REVISION || '';
if (previewRevision && !/^[a-f0-9]{40}$/.test(previewRevision)) throw new Error('Use a full public Git commit for the site preview.');
export const sourceRef = previewRevision || 'main';
export const sourceRepository = previewRevision ? `${repository}/tree/${sourceRef}` : repository;
export const sourceDoc = (path: string) => `${repository}/blob/${sourceRef}/${path}`;
const cloneCommands = [`git clone ${repository}.git`, ...(previewRevision ? [`git -C oci-founder-kit checkout --detach ${sourceRef}`] : [])];

export type Task = 'build' | 'migrate' | 'setup';
export type Agent = 'codex' | 'claude';
export type Stack = 'existing' | 'nextjs' | 'fastapi' | 'choose' | 'taskboard';
export type Project = 'new' | 'existing' | 'continue';
export type Stage = 'auto' | 'local-workflow' | 'access' | 'design-cost' | 'cloud-plan' | 'deployment' | 'recovery' | 'cutover' | 'acceptance';
export type Selection = { task: Task; agent: Agent; stack: Stack; project?: Project; stage?: Stage };
export type RouteSelection = Selection & { project: Project; stage: Stage };
export const defaultSelection: RouteSelection = { task: 'build', agent: 'codex', stack: 'existing', project: 'existing', stage: 'auto' };
const anchors = ['', 'main', 'start', 'build', 'migrate', 'setup', 'examples', 'guides', 'evidence'];
export const projects = { new: 'New project', existing: 'Existing project', continue: 'Continue' };
export const stages = {
  auto: { label: 'Find my next step', evidence: 'Inspect current code and local records. Identify the first unfinished checkpoint from actual evidence.', guide: 'docs/PROGRESS.md' },
  'local-workflow': { label: 'Useful local app', evidence: 'Source revision, build/test commands, and a demonstrated primary user flow.', guide: 'docs/PROJECT-BRIEF.md' },
  access: { label: 'Access and target', evidence: 'Readiness results and the selected auth method, region and compartment, confirmed privately.', guide: 'docs/START-HERE.md#oci-credentials-and-initial-setup' },
  'design-cost': { label: 'Design and cost', evidence: 'Five-pillar decisions, dated pricing, retained providers and unresolved risks.', guide: 'skills/oci-foundation/references/well-architected.md' },
  'cloud-plan': { label: 'Cloud plan', evidence: 'The exact current saved plan, expiry, resource changes and a separate owner decision.', guide: 'docs/START-HERE.md#deploy-verify-and-operate' },
  deployment: { label: 'Deployment verification', evidence: 'A private deployment receipt and running HTTPS, identity, permission and persistence checks.', guide: 'docs/OPERATIONS.md#before-real-users' },
  recovery: { label: 'Recovery and operations', evidence: 'Actual restore and rollback results, remaining resources, and an owner/runbook.', guide: 'docs/OPERATIONS.md' },
  cutover: { label: 'Migration cutover', evidence: 'Source/target parity, data checks, a rollback window and a separately approved traffic switch.', guide: 'docs/MIGRATION-ACCEPTANCE.md' },
  acceptance: { label: 'Production acceptance', evidence: 'Workload-specific security, recovery, cost and operational evidence accepted by the owner.', guide: 'docs/OPERATIONS.md#before-real-users' },
} satisfies Record<Stage, { label: string; evidence: string; guide: string }>;

// Only public choices cross this boundary. A stage is a requested focus, never progress or approval.
export function normalizeSelection(input: { task?: unknown; agent?: unknown; stack?: unknown; project?: unknown; stage?: unknown }): RouteSelection {
  const task = typeof input.task === 'string' && ['build', 'migrate', 'setup'].includes(input.task) ? input.task as Task : 'build';
  const agent = input.agent === 'claude' ? 'claude' : 'codex';
  let project: Project = typeof input.project === 'string' && ['new', 'existing', 'continue'].includes(input.project) ? input.project as Project : input.stack === 'taskboard' && task === 'build' ? 'new' : 'existing';
  if (task !== 'build' && project === 'new') project = 'existing';
  let stack: Stack = typeof input.stack === 'string' && ['existing', 'nextjs', 'fastapi', 'choose', ...(task === 'build' && project !== 'existing' ? ['taskboard'] : [])].includes(input.stack) ? input.stack as Stack : 'existing';
  if (project === 'new' && stack === 'existing') stack = 'choose';
  const stage = project === 'continue' && typeof input.stage === 'string' && Object.hasOwn(stages, input.stage) && (input.stage !== 'cutover' || task === 'migrate') ? input.stage as Stage : 'auto';
  return { task, agent, stack, project, stage };
}

export function readFragment(fragment: string): { anchor: string; selection: RouteSelection } {
  if (fragment.length > 300) return { anchor: 'start', selection: { ...defaultSelection } };
  const [candidate, query = ''] = fragment.replace(/^#/, '').split('?');
  const params = new URLSearchParams(query);
  return {
    anchor: anchors.includes(candidate) ? candidate : 'start',
    selection: normalizeSelection({ task: params.get('task'), agent: params.get('agent'), stack: params.get('stack'), project: params.get('project'), stage: params.get('stage') }),
  };
}

export function selectionFragment(input: Selection, anchor = 'start'): string {
  const { task, agent, stack, project, stage } = normalizeSelection(input);
  return `#${anchors.includes(anchor) ? anchor : 'start'}?task=${task}&agent=${agent}&stack=${stack}${project === 'existing' ? '' : `&project=${project}`}${stage === 'auto' ? '' : `&stage=${stage}`}`;
}

export const tasks = {
  build: { label: 'Build an app', goal: 'Build my application on OCI, starting with a working local version.', next: 'Open your existing app in your coding agent. Paste the prompt to inspect the project and define its next useful workflow.', example: 'A customer portal where clients can track projects, share files and leave feedback.' },
  migrate: { label: 'Migrate an app', goal: 'Migrate this existing application from Vercel or Netlify to OCI, starting with a read-only repository assessment.', next: 'Open your existing application repository in your coding agent. Paste this prompt to assess compatibility before changing anything.', example: 'Move my Next.js app from Vercel. Keep the existing database, sign-in and payments.' },
  setup: { label: 'Set up OCI', goal: 'Inspect my local prerequisites, guide initial account and administrator setup, then prepare a dedicated OCI environment.', next: 'Open a project folder in your coding agent. Start with local readiness checks, even without credentials or an environment, then follow the next account or administrator step.', example: 'I received my OCI welcome email. Help me set up access and a rehearsal environment for my startup.' },
} satisfies Record<Task, { label: string; goal: string; next: string; example: string }>;

const stackInstructions: Record<Exclude<Stack, 'taskboard'>, string> = {
  existing: 'Preserve the existing framework, database and identity provider unless I explicitly choose to change them.',
  nextjs: 'For a new application, use Next.js and TypeScript. For an existing app, assess its current stack before recommending changes.',
  fastapi: 'For a new application, use Python and FastAPI. For an existing app, assess its current stack before recommending changes.',
  choose: 'Recommend a small, maintainable stack after reviewing the requirements and any existing code. Explain the tradeoffs.',
};

export function checkpoint(raw: Selection): { title: string; results: string[]; guide: string; guideLabel: string } {
  const input = normalizeSelection(raw);
  if (input.project === 'continue') return {
    title: input.stage === 'auto' ? 'One evidence-backed next step' : `Review: ${stages[input.stage].label.toLowerCase()}`,
    results: [stages[input.stage].evidence, 'Recheck recorded results against current source. Keep missing or stale checks unfinished.'],
    guide: stages[input.stage].guide, guideLabel: input.stage === 'auto' ? 'Progress and evidence guide' : 'Read the checkpoint guide',
  };
  if (input.task === 'migrate') return { title: 'A migration assessment you can act on', results: ['A dependency inventory, retained services and missing facts.', 'A local validation plan, staging steps and a rollback boundary.'], guide: 'docs/MIGRATION-ACCEPTANCE.md', guideLabel: 'Migration acceptance guide' };
  if (input.task === 'setup') return { title: 'Your first OCI step, clearly explained', results: ['Local prerequisite results and the missing choices for the current phase.', 'An administrator handoff for initial users, groups, parent compartment and scoped access.'], guide: 'docs/NEW-OCI-ACCOUNT.md', guideLabel: 'New OCI account guide' };
  if (input.stack === 'taskboard') return { title: 'Your own editable Taskboard project', results: ['App source in app/, infrastructure in terraform/, and agent skills in your project.', 'With Docker running: add, rename and complete a task locally; record the result.'], guide: 'blueprints/fullstack-container/LOCAL.md', guideLabel: 'Local preview requirements' };
  return { title: 'One useful workflow, running locally', results: ['A working app flow you can try, with its local start command.', 'Actual test results and unfinished checks in your project’s progress record.'], guide: 'docs/PROJECT-BRIEF.md', guideLabel: 'Define your first workflow' };
}

export function handoff(raw: Selection) {
  const input = normalizeSelection(raw);
  const continuing = input.project === 'continue';
  const taskboard = input.task === 'build' && input.stack === 'taskboard';
  const next = continuing
    ? 'Open the same app folder in your agent. Paste the continuation prompt. It rechecks local records and current code before choosing the next action.'
    : input.project === 'new'
      ? taskboard ? 'Tell your agent the new project path, or open an empty folder. Paste the prompt to create your editable Taskboard without replacing an existing app.' : 'Create an empty app folder and open it in your agent. Paste the prompt to agree and build the first useful workflow in your chosen stack.'
      : tasks[input.task].next;
  return {
    title: continuing ? 'Pick up with a clear next step.' : input.task === 'setup' ? 'Make your first OCI steps clear.' : input.project === 'new' ? 'Give your idea a working first version.' : 'Move your existing project forward.',
    next,
    summary: continuing ? `Focus: ${stages[input.stage].label.toLowerCase()}. Your agent checks the evidence before continuing.` : taskboard ? 'An editable Node.js/PostgreSQL app, installed skills, then a separate local Docker preview.' : tasks[input.task].goal,
    prerequisites: continuing
      ? ['The same app folder and your coding agent.', 'Existing progress is context; current checks establish what is ready.', 'A missing local project record is a recovery step, not a reason to recreate the app.']
      : [input.project === 'new' ? 'A new or empty app folder, outside the kit checkout.' : 'An existing app folder; an empty folder also works for OCI setup.', 'Git, Python 3.11+ and your coding agent account. Linux is tested; macOS/WSL2 acceptance is pending.', input.task === 'setup' ? 'Initial inspection needs no OCI credentials. You complete account sign-in and approve access changes.' : taskboard ? 'Running the preview also needs local Docker and Compose.' : 'Your app’s runtime for local tests. OCI access can be configured later.'],
    terminalHelp: continuing
      ? 'Run from the same app folder. List the existing environments first, then replace ENVIRONMENT with the intended named target. Next refreshes local records without running app tests or cloud operations. For an older project with no named environments, omit the flag only after inspection. If this kit version or its saved project record is absent, use the continuation prompt to inspect and recover the existing project first.'
      : input.task === 'setup'
        ? 'Run the inspection from a reviewed checkout outside your app. Replace the example project path. No environment or credential profile is required, and no cloud request runs. Follow the new-account guide to prepare a named environment after inspection.'
      : taskboard
        ? 'Run from outside the target project. Replace the example path with a new folder under an existing parent, or an empty existing folder. Creation is offline; existing files are never overwritten. Starting the preview is a separate step.'
        : input.project === 'new' ? 'Run from outside the target project. Use a new folder under an existing parent or an empty existing folder. The helper creates the project record and skills, with no generated app unless you explicitly chose Taskboard.' : 'Run from outside your app folder. The target folder must already exist. Replace the example path with its absolute path. If already installed, choose Continue; do not remove existing files to make installation pass.',
  };
}

export function createPrompt(raw: Selection & { brief: string }): string {
  const input = normalizeSelection(raw);
  if (input.project === 'continue') return resumePrompt(input) + (raw.brief.trim() ? `\n\nAdditional context: ${raw.brief.trim().slice(0, 1200)}` : '');
  const task = tasks[input.task];
  const entry = input.agent === 'codex' ? '$oci-kit' : '/oci-kit';
  const taskboard = input.task === 'build' && input.stack === 'taskboard';
  const brief = raw.brief.trim().slice(0, 1200);
  const lines = [
    `Read ${sourceRepository} and follow its README installation instructions.`,
    ...(previewRevision ? [`For this preview, use the reviewed kit at commit ${sourceRef}. Inspect an existing installation and use the supported update path if needed.`] : []),
    'Inspect the project and any existing OCI Founder Kit installation first. If installed, check its status and use its current skills; do not reinstall or overwrite it.',
    input.project === 'new' ? 'I am starting a new project. Use my intended empty project folder; preserve any existing files if the folder is not empty.' : 'I am working in an existing project. Preserve its source, instructions, services and uncommitted work.',
    ...(taskboard ? [
      `I explicitly choose the editable Node.js/PostgreSQL Taskboard starter. From a kit clone outside my target project, run python3 scripts/kit.py start --project /absolute/path/to/my-app --task build --mode new --agent ${input.agent} --blueprint fullstack-container, replacing the example path with my intended project path.`,
      'Use a new folder under an existing parent or an empty existing folder. Refuse any overwrite. If the app already exists, inspect it and continue without regenerating it.',
      'Creation copies files and skills offline; it does not start Docker or deploy anything. Edit the project’s app/ and terraform/ files, not the hidden kit’s reference copy.',
      'From the created project, use python3 local_preview.py start when Docker and Compose are available. Explain missing prerequisites; do not claim the preview ran if it did not.',
    ] : input.task === 'setup' ? [
      'From the installed kit or a reviewed checkout outside the app, run python3 scripts/kit.py onboard inspect --project /absolute/path/to/my-app, using the actual kit and application paths. This works before installation, credentials or a named environment exist.',
      `After inspection, use onboard prepare only with my intended environment name and role, --mode existing --task setup --agent ${input.agent}. It adds local kit files and a generic deployment target without replacing my application or making cloud changes.`,
    ] : [`If the kit is absent, install into this project for ${input.agent === 'codex' ? 'Codex' : 'Claude Code'}, preserving existing instructions and skills. Use python3 scripts/project.py start --project /absolute/path/to/my-app --task ${input.task} --mode ${input.project} --agent ${input.agent} --stack ${input.stack === 'nextjs' || input.stack === 'fastapi' ? input.stack : input.stack === 'existing' ? 'custom' : 'auto'} from a reviewed kit clone outside the app, replacing the example path.`]),
    `Then use ${entry}: ${task.goal}`,
    'Use the reviewed project helper to maintain a local project record when available. Its status and resume commands inspect local records; they do not run tests, detect a live deployment or approve cloud changes.',
  ];
  if (input.task === 'build' && input.stack === 'nextjs') {
    lines.push('Follow docs/OWN-APP-LAUNCH.md. Use my Next.js app and its existing tests. Run doctor, journey and cost preview for the named rehearsal, then report what my 24-hour demo and 30-day deployment would cost.');
  }
  if (brief) lines.push('', `My project brief: ${brief}`);
  lines.push('');
  if (input.task !== 'setup' && !taskboard) lines.push(stackInstructions[input.stack === 'taskboard' ? 'existing' : input.stack]);
  if (input.task === 'build') lines.push('Agree the smallest useful app, implement it, and run meaningful local tests. Include responsive layouts and clear empty, loading and error states.', 'Keep local development moving while OCI setup is incomplete.');
  else if (input.task === 'migrate') lines.push('Inventory provider-specific features and environment variable names without exposing values. Preserve source behavior, data, identity and integrations.', 'Move hosting first; retain the existing database, storage and sign-in provider. Adapt and test locally, then use separate source, rehearsal and production environments. Migrate data only in a later tested step after hosting acceptance.', 'Attach the reusable web-container deployment target without replacing app code. Compare source and target HTTP and browser workflows, keep target jobs disabled until ownership transfers, and prepare separate traffic cutover and rollback steps. Do not change DNS or production data without separate approval.');
  else lines.push('Start with offline tool and configuration checks. Group the missing nonsecret choices for the current phase; keep later requirements visible without blocking unrelated local work.', 'Follow docs/NEW-OCI-ACCOUNT.md for welcome-email activation, browser sign-in, and the initial parent compartment and human group/membership steps. The owner or authorized administrator performs those reviewed Console changes; do not assume they already exist or bypass the deployment gate.', 'Reuse approved resources, prepare scoped IAM and cost guidance, and keep denied access or unavailable capacity explicitly unknown. A local inspection is not a live OCI verification.');
  lines.push(`First checkpoint: ${checkpoint(input).title}.`, 'Create or update docs/PROGRESS.md in this application using the kit’s progress guide. Preserve existing records; include actual commands/results, unfinished checks and one next action. Keep private evidence outside Git.', 'Use OCI Well-Architected guidance. Show the exact target, permissions, resources, dated cost estimate and plan before any cloud changes; wait for my approval.', 'Never ask me to paste private keys, passwords or tokens. Keep credentials, state and private receipts out of chat and Git.', 'Finish with what was tested, what is still unverified, and the next action.');
  return lines.join('\n');
}

export function resumePrompt(raw: Selection): string {
  const input = normalizeSelection({ ...raw, project: 'continue' });
  const entry = input.agent === 'codex' ? '$oci-kit' : '/oci-kit';
  return [
    `Use ${entry} to continue this project’s ${input.task === 'setup' ? 'OCI setup' : input.task === 'migrate' ? 'migration to OCI' : 'local app build and OCI preparation'}.`,
    'Inspect the existing code, project instructions, kit installation status and docs/PROGRESS.md first. Use the installed skills; do not reinstall, regenerate the app or overwrite existing work.',
    'Inspect scripts/kit.py environment list first. Select the intended named environment explicitly for status and next; never fall back to legacy progress or choose production automatically. A missing saved record requires inspection of existing work, not a fresh app creation. Keep local records private.',
    ...(input.task !== 'setup' ? [input.stack === 'taskboard' ? 'Continue editing this project’s Taskboard app/ and terraform/ files. Keep its Node.js/PostgreSQL stack; do not edit the hidden kit’s reference copy.' : stackInstructions[input.stack]] : []),
    ...(input.stage !== 'auto' ? [`My requested focus is ${stages[input.stage].label.toLowerCase()}. This selection is not evidence of completion or approval.`, `Evidence to check: ${stages[input.stage].evidence}`, 'Verify prerequisites and earlier unfinished checkpoints before continuing this stage.'] : []),
    'Treat recorded results as evidence to review, not proof of current readiness. If the progress record is missing, reconstruct a short record from the code and actual checks without inventing completed work.',
    'State the first unfinished checkpoint and continue the useful local work. Update the progress record with what was tested, what is still unverified, and the next action.',
    'Use OCI Well-Architected guidance. Past approvals do not authorize new cloud changes. Show the exact current target, permissions, resources, dated costs and plan; wait for my approval before cloud writes.',
    ...(input.task === 'migrate' ? ['Continue hosting first, retaining database, storage and sign-in. Select the named environment explicitly, recheck source/target behavior and scheduler ownership, and keep data migration separate. Do not change DNS or production data without separate approval.'] : []),
    'Never ask me to paste private keys, passwords or tokens. Keep credentials, state and private receipts out of chat and Git.',
  ].join('\n');
}

export function installCommand(agent: Agent, stack: Stack = 'existing', project: Project = 'existing'): string {
  if (project === 'continue') return ['python3 .oci-founder-kit/scripts/kit.py environment list --project .', '# Replace ENVIRONMENT with the existing target you intend to continue.', 'python3 .oci-founder-kit/scripts/kit.py next --project . --environment ENVIRONMENT'].join('\n');
  return [...cloneCommands, stack === 'taskboard' ? 'python3 oci-founder-kit/scripts/blueprint.py create fullstack-container \\' : 'python3 oci-founder-kit/scripts/install.py \\', `  --project /absolute/path/to/my-app --agent ${agent}`, 'cd /absolute/path/to/my-app'].join('\n');
}

export function projectCommand(raw: Selection): string {
  const input = normalizeSelection(raw);
  if (input.project === 'continue') return installCommand(input.agent, input.stack, 'continue');
  if (input.task === 'setup') return [
    ...cloneCommands,
    'python3 oci-founder-kit/scripts/kit.py onboard inspect \\',
    '  --project /absolute/path/to/my-app',
  ].join('\n');
  const stack = input.stack === 'nextjs' || input.stack === 'fastapi' ? input.stack : input.stack === 'existing' ? 'custom' : 'auto';
  return [
    ...cloneCommands,
    'python3 oci-founder-kit/scripts/kit.py start \\',
    `  --project /absolute/path/to/my-app --mode ${input.project} \\`,
    `  --task ${input.task} --agent ${input.agent} --stack ${stack}${input.stack === 'taskboard' ? ' --blueprint fullstack-container' : ''}`,
    'cd /absolute/path/to/my-app',
  ].join('\n');
}
