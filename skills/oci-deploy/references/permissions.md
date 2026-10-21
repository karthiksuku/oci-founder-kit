# A second lock: ask before apply

The gate refuses any plan the owner has not approved. A permission rule in
the coding agent adds a second, independent check: the harness itself asks
before the apply or destroy command runs.

## Claude Code

Add to the project's `.claude/settings.json` (or the user settings):

```json
{
  "permissions": {
    "ask": [
      "Bash(python3 *deploy_gate.py apply*)",
      "Bash(python3 *deploy_gate.py destroy *)",
      "Bash(terraform apply*)",
      "Bash(terraform destroy*)"
    ]
  }
}
```

Do not add these commands to an allow list. With the `ask` rule, every apply
shows the exact command, including the plan hash, for a click to approve.

## Codex

Run Codex with an approval policy that asks before running commands that
change state, and do not add the gate's apply or destroy commands to any
trusted command list.

## What this does not replace

The owner still needs to read the plan summary. A permission prompt shows the
command; the summary shows what the command will do.
