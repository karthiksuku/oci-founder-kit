# A second lock: ask before apply

The gate checks the saved plan hash, expiry and one-attempt use. It cannot
prove a person approved a hash that the agent can also read. Explicit owner
approval in the conversation and an independent coding-agent permission prompt
are required before apply or destroy.

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
