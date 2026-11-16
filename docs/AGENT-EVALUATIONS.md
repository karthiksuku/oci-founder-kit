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

Use a fresh workspace for every agent/scenario trial. Replace `claude` with
`codex`, and choose `hosting-first`, `unsupported` or `interrupted` for migration
and failure cases. Agent runtime is bounded at 30–900 seconds; output and tool
calls also have limits. A failed capability configuration must stop the session;
never retry with broader permissions or bypass hook trust. CLI authentication
and subscriptions may incur normal model usage.

| Scenario | Independent outcome checks |
|---|---|
| New app | Browser creation/completion of checklist tasks, reload persistence, blank-input rejection and text rendering; three explicit environments; two separate web-container attachments |
| Hosting first | Existing app files remain byte-identical; known container example still passes loopback route, cache, redirect, access-denial and streaming checks; compatibility report and explicit hosting/data/job-owner boundary |
| Unsupported dependency | Existing source preserved; compatibility evidence exists and cutover remains blocked |
| Interrupted operation | A simulated response is lost after local initialization; the agent inspects/resumes committed progress without overwriting the app |

The evaluation-only MCP tool permits bounded public source reads, a few fixture
app writes, and fixed local kit actions. It has no arbitrary shell, credential,
cloud or publishing capability. Claude uses restricted file/tool access and an
explicit MCP allowlist. Codex runs with shell, apps, plugins, browsing and
delegation disabled and a read-only built-in sandbox; its sole eval MCP tool has
fixed operations. These settings intentionally differ from ordinary unrestricted
founder sessions and must be disclosed with results.

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
Broader acceptance still needs real OCI HTTPS, hosted identity, two-user
isolation, persistence, isolated restore, image rollback, traffic rollback and
reviewed retained-resource/cost evidence.

The harness follows outcome-based evaluation guidance: distinguish generated
artifacts and independently tested behavior from the agent's own claims.
See [OpenAI skill evaluations](https://developers.openai.com/blog/eval-skills)
and [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
