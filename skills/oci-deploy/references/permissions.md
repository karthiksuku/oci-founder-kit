# Ask before a gated cloud operation

The gate checks the saved plan hash, expiry and one-attempt use. It cannot
prove a person approved a hash that the agent can also read. Explicit owner
approval in the conversation and an independent coding-agent permission prompt
are required before apply, destroy, image publication or `backend-run`.
`backend-plan` prepares its packet offline; `backend-run` can initialize a remote
backend or create/delete lock objects while generating a resource plan. Approval
of that backend operation does not approve the resulting resource apply.

## Claude Code

Add to the project's `.claude/settings.json` (or the user settings):

```json
{
  "permissions": {
    "ask": [
      "Bash(python3 *deploy_gate.py apply*)",
      "Bash(python3 *deploy_gate.py destroy *)",
      "Bash(python3 *deploy_gate.py image-push*)",
      "Bash(python3 *deploy_gate.py backend-run*)",
      "Bash(terraform apply*)",
      "Bash(terraform destroy*)",
      "Bash(terraform init*)",
      "Bash(terraform plan*)",
      "Bash(terraform state*)",
      "Bash(terraform workspace*)",
      "Bash(terraform force-unlock*)"
    ]
  }
}
```

Do not add these commands to an allow list. Check the installed harness's actual
matching behavior, including global flags such as `-chdir`; a command pattern
is not a security sandbox. The prompt is an additional control, not permission
to run direct remote Terraform operations instead of the gate.

## Codex

Run Codex with an approval policy that asks before running commands that
change state, and do not add the gate's apply, destroy, backend-run or image-push commands to any
trusted command list.

## What this does not replace

The owner still needs to read the plan summary. A permission prompt shows the
command; the summary shows what the command will do.
Review [backend destination, inherited IAM and retention](backend-state.md)
separately. The kit does not provide gated state migration, state push, workspace
changes, force-unlock or version cleanup; a permission prompt does not add that
missing implementation or establish a safe operation scope.
