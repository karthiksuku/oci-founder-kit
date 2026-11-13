# Start with a useful app

Copy this short brief into your application's documentation. Fill what you know;
your agent should inspect the project before asking questions already answered
by its source. An idea or an exported Launchpad Studio brief is enough to begin.

```markdown
# Project brief

Outcome: What should someone be able to accomplish?
Users: Who uses it, and which actions belong to each role?
First useful workflow: The smallest complete experience to build and test.
Acceptance: A concrete action and observable result, including failure behavior.

Existing project: Framework/runtime, working features and current test command.
Keep: Database, identity, storage, payments or other services to retain.
Change: What is explicitly in scope to build or migrate.
Data: Sensitivity, ownership, retention and nonproduction test-data source.
Design: Existing design system or a simple visual direction; mobile requirements.
Operations: Intended users/traffic, latency needs, recovery objectives and owner.
Budget: Currency and a target range to check with current prices, not a guarantee.

Open decisions: Only missing facts that materially affect implementation.
First checkpoint: A local app action we can demonstrate before cloud deployment.
```

Use environment variable **names**, never values. Keep private account settings,
state and credentials outside this brief. Don't choose a database or Kubernetes
before the workload needs it. Keeping the existing identity or database can be
the best first migration step.

Give the brief to your agent:

```text
Use oci-kit and this project brief. Inspect the existing app, preserve its
instructions and stack, and implement the first useful workflow locally.
Show actual test results and the next action. Prepare OCI setup and a reviewed
deployment plan when the app is ready; keep cloud writes approval-gated.
```

Track results using the [progress record](PROGRESS.md). For an existing hosted
app, add the [migration acceptance record](MIGRATION-ACCEPTANCE.md).
