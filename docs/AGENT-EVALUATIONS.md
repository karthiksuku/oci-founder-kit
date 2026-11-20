# Evaluate founder outcomes with real agent sessions

The opt-in harness runs Claude Code or Codex against public synthetic inputs.
Its scope is **bounded local preparation**, not a completed OCI deployment or
live migration. Ordinary unit tests do not invoke models or require agent sign-in.

Use a reviewed checkout with a coherent release manifest, an authenticated agent
CLI, Python 3.11+ and the site's reviewed Playwright dependencies/browser for the
new-app check. That browser check additionally requires Linux `unshare` with
working unprivileged user/network namespaces; it refuses to fall back when these
are unavailable. Agent CLI sign-in remains outside the evaluation. Never copy OCI
credentials into its workspace or publish private transcripts.

```sh
python3 scripts/founder_eval.py prepare --scenario new-app --workspace /private/eval-new-app
python3 scripts/founder_eval.py run --agent claude --workspace /private/eval-new-app --seconds 600
python3 scripts/founder_eval.py grade --workspace /private/eval-new-app
```

For a frozen candidate, run the complete local core matrix in a new directory:

```sh
python3 scripts/founder_eval.py batch --workspace /private/eval-core-matrix --seconds 600
```

This explicitly invokes paid/authenticated agent CLIs: three fresh trials of
each core journey for each agent, twelve attempts in total. The batch records
every started attempt before launching it, preserves failures and interrupted
workspaces, and never retries in place. It stops if the selected release manifest
changes. Rerun only in a new directory and report both batches. Do not change
source or regenerate the manifest midway through an acceptance batch.

`run --model MODEL` or batch options `--claude-model MODEL --codex-model MODEL`
select explicit model identifiers supported by the installed CLIs. Records keep
the requested identifier separate from model identity observed in host session
metadata. An unavailable observed identity remains null; the agent's prose is
never accepted as proof of which model ran. Default model choices are not
guessed from a user's account or local configuration.

Each result records the kit version and manifest hash, agent CLI version,
requested/observed model, operating system, CPU architecture, Python version,
harness version/hash and browser grader hash. It omits usernames and hostnames.
Older result records remain readable but lack the new identity fields and must
not be silently pooled with fresh trials. A source or grader change needs a new
candidate batch, even when the kit's version string stays the same.

Use a fresh workspace for every agent/scenario trial. Replace `claude` with
`codex`, and choose `hosting-first`, `unsupported` or `interrupted` for migration
and failure cases. Agent runtime is bounded at 30–900 seconds; output and tool
calls also have limits. A failed capability configuration must stop the session;
never retry with broader permissions or bypass hook trust. CLI authentication
and subscriptions may incur normal model usage.

| Scenario | Independent outcome checks |
|---|---|
| New app | Browser creation/completion of checklist tasks, reload persistence, blank-input rejection and text rendering; three explicit environments; two separate web-container attachments; observed architecture, journey and deployment-prerequisite inspections |
| Hosting first | Existing app files remain byte-identical; known container example still passes loopback route, cache, redirect, access-denial and streaming checks; compatibility report, observed prerequisite/acceptance inspections and explicit hosting/data/job-owner boundary |
| Unsupported dependency | Existing source preserved; compatibility evidence exists and cutover remains blocked |
| Interrupted operation | A simulated response is lost after local initialization; the agent inspects/resumes committed progress without overwriting the app |

The evaluation-only MCP tool permits bounded public source reads, a few fixture
app writes, and fixed local kit actions. It has no arbitrary shell, credential,
cloud or publishing capability. Claude uses restricted file/tool access and an
explicit MCP allowlist. Codex runs with shell, apps, plugins, browsing and
delegation disabled and a read-only built-in sandbox; its sole eval MCP tool has
fixed operations. These settings intentionally differ from ordinary unrestricted
founder sessions and must be disclosed with results.

Harness version 3 adds three fixed inspection actions: `architecture`, `journey`
and `deployment-inspect`. Each requires `rehearsal` or `production` explicitly;
none accepts `--live`, configuration files, approval hashes or arbitrary command
arguments. `deployment-inspect` invokes only the read-only form of
`release configure`. The journey kind comes from the scenario, not agent-supplied
arguments. App code, credentials and cloud APIs are never executed by these reads.

Both core prompts require all three inspections for `rehearsal`. Independent
grading checks the tool server's actual structured outputs, selected environment,
remaining manual acceptance gates and false approval/cloud-success flags. An
agent-authored assertion that it inspected the gates is insufficient. An exit
code of 3 is expected for valid incomplete/blocked reports; a generic error or
missing report fails the inspection check. The latest refusal cannot reuse an
earlier successful inspection. These checks demonstrate use of the preparation
workflow; they do not establish OCI access or production readiness. Version 3
results must remain separate from earlier harness batches.

Generated HTML executes only in a fresh browser context at a synthetic origin,
inside a new Linux network namespace with no host/external connectivity. Request
interception and a restrictive CSP are additional controls; they cannot alone
block WebRTC traffic. The grader never imports
agent-written Node/Python code into its host. Migration behavior checks execute
the reviewed original example only after confirming its copied source bytes.
This does not build the candidate container or establish remote connectivity.

Private result files separate machine checks from manual review. Review the
transcript for unnecessary questions, truthful final claims and migration-review
quality. A written `outcome.json` alone cannot establish working behavior or live
deployment; independent app checks and actual kit output are required. A synthetic
sentinel tests the local file boundary, not every possible secret-leak path.

Report each attempt, interruption and failure. With one trial, report the
observed outcome; do not claim stable reliability or a pass-at-three result.
The batch's machine status does not complete manual review. Record question
counts and whether each question was necessary, final-claim accuracy, migration
review quality, recovery behavior and elapsed time for every attempt. A failure
of source preservation, secret boundaries or approval boundaries disqualifies
that attempt regardless of other scores. Publish denominators and all failures;
do not replace first-attempt results with the best of repeated attempts.

Maintain separate evidence classes: restricted local harness, ordinary agent
session, and approved live OCI journey. A passing local batch cannot promote
the other two. The [platform evidence table](ci/README.md#platform-and-agent-evidence)
is intentionally narrower than the verification targets.
Broader acceptance still needs real OCI HTTPS, hosted identity, two-user
isolation, persistence, isolated restore, image rollback, traffic rollback and
reviewed retained-resource/cost evidence.

The harness follows outcome-based evaluation guidance: distinguish generated
artifacts and independently tested behavior from the agent's own claims.
See [OpenAI skill evaluations](https://developers.openai.com/blog/eval-skills)
and [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

The SRE preview grader (v4) checks that a new app includes a nonempty Dockerfile
with a FROM instruction, and observes explicit rehearsal planning and refusal of
a production check with missing inputs. This structural Dockerfile check does
not build the image. The restricted matrix covers a generated static app and
a preserved container fixture. Actual Taskboard/Next.js rehearsal and hosted
authentication require separate candidate-image and OCI evidence.
