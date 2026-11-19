# Review architecture with evidence

The private architecture report connects Oracle's Well-Architected guidance to
the selected environment's existing readiness and operating reports. It shows
what has been observed, what is only configured, and what still needs a person or
a workload-specific test. It assigns no score and grants no deployment approval.

From the application directory, run:

```sh
python3 .oci-founder-kit/scripts/kit.py architecture --environment rehearsal --json
```

The environment is mandatory. The retained source environment cannot be selected
as an OCI target. This command reads local private records only: it performs no
cloud requests, executes no application commands, writes no files and reads no
credential values. Reports remain local; nothing is uploaded automatically.

## What the report covers

The control groups follow Oracle's current five pillars:

| Pillar | Selected evidence and remaining work |
| --- | --- |
| Security and compliance | Private app subnet and registry metadata, certificate expiry; effective IAM, state isolation and hosted two-user access still require separate verification. |
| Reliability and resilience | Selected instance and load-balancer health; recovery checkpoints remain owner records, and isolated restore, image rollback, capacity and redundancy need workload acceptance. |
| Performance and cost optimization | Configured sizing, selected utilization observations and scoped Usage API cost evidence; missing billing access remains unknown. |
| Operational efficiency | Actual image readback against the current deployment receipt, recent work requests and explicit environment selection. |
| Distributed cloud | External dependency connectivity, source-versus-target parity and background-job ownership for hosting-first migration. |

The mapping is original kit code based on [Oracle's public Well-Architected
framework](https://docs.oracle.com/en/solutions/oci-best-practices/index.html),
reviewed **19 November 2026**. It is a selected-control review, not the full
framework or an Oracle certification.

## Read the evidence level before acting

| Status | Meaning |
| --- | --- |
| `observed` | A current local report records the selected live read. This establishes only that narrow metadata or operating check. |
| `configured` | Valid private configuration exists; runtime behavior is not established. |
| `tested` | A complete, uninterrupted selected-origin HTTPS migration report passed. Local loopback tests cannot establish this target-bound result. |
| `owner-recorded` | A person recorded recovery or cost evidence; it has not become independent verification. |
| `failed` | A selected check reported a failure requiring review. |
| `stale` | The relevant evidence is old, belongs to a changed source/target/toolkit, or no longer matches the current deployment receipt. |
| `unknown` | Evidence is missing, denied, ambiguous, malformed or insufficient for this control. |
| `not-applicable` | The selected project is not performing the hosting-migration journey. This status applies only to its parity control. |

Each control includes a responsible role, an action and an environment-specific
recheck command. Available evidence references contain a content hash, schema,
timestamp, age and evidence mode. They exclude account/resource identifiers,
hostnames, application source, raw logs, arbitrary error messages and credentials.
The underlying private report retains the bindings needed for review.

Reports must match the current source, toolkit and complete environment
configuration, and be no older than 24 hours. Equal newest timestamps are
ambiguous. An invalid newest report does not fall back to an older successful
report. Operating observations additionally require the current accepted
deployment receipt; injected test clients never establish live observations.
Changing source, image, environment, toolkit or the deployment attempt requires
fresh evidence. Local report files are not authenticated attestations.

## Refresh the specific evidence

Use the selected environment's existing commands:

```sh
python3 .oci-founder-kit/scripts/kit.py doctor --environment rehearsal --live
python3 .oci-founder-kit/scripts/kit.py observe --environment rehearsal --live
python3 .oci-founder-kit/scripts/kit.py verify --environment rehearsal
python3 .oci-founder-kit/scripts/kit.py architecture --environment rehearsal --json
```

The first two commands make bounded reads when explicitly requested and when
their prerequisites are present. Operating observations require a current bound
deployment receipt. Migration verification additionally needs the reviewed
private contract and any private sessions; follow the
[migration acceptance guide](MIGRATION-ACCEPTANCE.md).

Effective IAM isolation, hosted authentication, two-user authorization, isolated
restore and scheduler ownership cannot turn green just because Terraform files,
policy templates or a generic health endpoint exist. The report keeps these
controls unknown until dedicated evidence support exists. The default
single-instance path can interrupt service during replacement. Reported usage is
neither a final invoice nor a spending cap. Infrastructure changes, traffic
changes, synthetic writes and cleanup retain their exact-plan approval gates.
