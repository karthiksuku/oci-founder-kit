# Launch the Next.js app in your own repository

Start in the app you want to ship. Give Claude Code or Codex this prompt:

> Use OCI Founder Kit to launch my Next.js app. Preserve my existing code, tests,
> sign-in provider and data services. Start the app locally and test one real user
> action. Prepare an isolated rehearsal, show the cost of one day and thirty days,
> and give me the exact approval request before each cloud write. When a step needs
> an administrator, give me one handoff and the command to recheck it.

Use a reviewed kit checkout outside the app. The following prepares local configuration
for an existing app whose **hosting on OCI is new**. For a move from another host, select
the migration workflow and retain the original hosting until cutover acceptance.

~~~sh
python3 /path/to/oci-founder-kit/scripts/kit.py onboard prepare --project . \
  --task build --stack nextjs --role rehearsal --environment rehearsal --agent both
.oci-founder-kit/scripts/oci-kit doctor --environment rehearsal
.oci-founder-kit/scripts/oci-kit sre plan --environment rehearsal
.oci-founder-kit/scripts/oci-kit journey --environment rehearsal --kind build
.oci-founder-kit/scripts/oci-kit cost preview --environment rehearsal
~~~

| Milestone | What to keep as private evidence |
|---|---|
| Working app | Record the starting Git revision, existing test command and result, then run the app and perform one customer task. Identify existing identity, database and storage services. Run packaging inspection and review the proposed additive files before applying them. |
| Rehearsal | Agree on the hostname, certificate renewal owner, TLS and identity callback URLs. Verify least-privilege state access and compartment isolation. Prepare [deployment inputs](DEPLOYMENT-CONFIGURATION.md), review [one day and thirty days of costs](LAUNCH-COST.md), then obtain each separate cloud approval. Bind the exact image digest to this rehearsal. |
| First user | Verify the HTTPS hostname and certificate chain, sign-in, callback, logout, and two-user isolation. Prove the critical task and persistence using synthetic accounts. For an invited tester follow the [private customer trial](CUSTOMER-TRIAL.md). |
| Recovery and production | Restore to an isolated target. Rehearse rolling back to a previously accepted digest and test the customer action again. Bind the independent evidence to the pending **production** plan and separate rehearsal receipt via the [protected verifier](SRE-VERIFIER.md). The operator still needs approval of that exact plan. |
| Close the trial | Revoke tester access, check retained resources against scoped readbacks and billing, and record the timestamp of each observation. Obtain a new approval for any cleanup. |

## Record a launch others can reproduce

Start a private note when the founder opens the kit. For each milestone record its start and finish,
whether it passed, the evidence reference, and who had to intervene. Record installation/download time
and time waiting for an administrator separately. On failure record the symptom, recovery action and
the result of retrying. Compare the dated estimate with reported usage for the same period, noting
billing delay and retained charges. Keep account identifiers, hostnames, customer data and raw logs
out of a public write-up.

A publishable launch story includes the permitted public starting repo and revision, exact prompt,
elapsed time, estimated and observed cost, interventions, the rollback result and remaining resources.
The [gallery](https://karthiksuku.github.io/oci-founder-kit/#examples) starts with local reference
workflows. The first live founder launch record must come from an approved OCI trial.
