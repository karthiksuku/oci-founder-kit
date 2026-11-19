# 0.9.0 preview: connect setup, deployment inputs and acceptance evidence

This preview builds on the new-account workflow. It connects scoped operator
roles and selected foundation resources to private deployment configuration,
then shows what is and is not established by the available evidence.

## What changed

- [Deployment configuration](DEPLOYMENT-CONFIGURATION.md): `release configure`
  inspects missing choices, prepares a reviewed local proposal and generates
  owner-only deployment/backend inputs. It preserves existing application code,
  resource selections and automatic Terraform inputs. Existing runtime IAM remains
  an administrator prerequisite. No cloud operation runs during preparation.
- [Operator roles](../blueprints/workload-access/README.md): explicit app-deployer,
  state-operator and image-publisher proposals join foundation-provisioner and
  observer. Access becomes a separate foundation component using an explicitly
  selected administrator context in the home region. Handoff does not retarget
  the application to that identity or assert effective permissions.
- [Well-Architected report](WELL-ARCHITECTED-REPORT.md): `architecture` maps current
  bound evidence to Oracle's five pillars. Missing, stale, failed and unknown
  controls remain visible. Owner records do not become authenticated proof or
  certification.
- [Founder journey](FOUNDER-JOURNEY.md): `journey --kind build|migrate` shows
  prerequisite coverage and the next acceptance requirement. Local preparation,
  restricted agent trials and live OCI evidence remain separate. Incomplete
  reports return a nonzero status without discarding their diagnostic detail.
- Public Terraform environment settings reject common credential-key names,
  including API_KEY and AUTHORIZATION. This is a conservative filter, not a proof
  that arbitrary application settings contain no secrets.

- OCI command runners leave interactive auto-prompt disabled by removing its
  environment variable. Setting it to the string False can activate the installed
  CLI interactive mode; bounded read-only checks now avoid that local failure.

## Evidence and limits

The public release record carries exact source identity, test outcomes,
distribution hashes and any skipped checks. Tests cover configuration preservation,
existing gate compatibility, conflicting and stale selections, interrupted work,
credential-shaped inputs, scope isolation, ambiguous reports and privacy.
Terraform mock plans validate local contracts; they do not evaluate OCI's actual
IAM authorization decisions.

The complete welcome-email-to-HTTPS and hosting-first journeys still require
approved live acceptance: effective IAM, hosted sign-in, two-user isolation,
persistence, isolated recovery, image/traffic rollback and retained resources.
The evidence reports deliberately remain incomplete where those contracts or
observations are absent. They cannot establish full acceptance from a saved
preference, a passing unit test or an owner-supplied boolean.

Human enrollment, initial parent administration, certificate setup, runtime
identity and DNS remain explicit responsibilities. Cloud/IAM writes, backend
operations, traffic changes and destructive cleanup retain exact-plan approval.
Image publication permissions include OCI's broader image-update authority,
and app deployment authority can indirectly exercise its runtime identity;
review these boundaries in the role guide.

Hosted validation and authenticated release attestations require a
workflow-authorized GitHub credential. Prepared definitions are not successful
workflow runs. Checksums establish byte identity, not publisher provenance.
macOS/WSL2 and ordinary-agent acceptance are unverified unless the dated release
record explicitly records an actual completed test of that combination.

Only public sources and original kit code are used. This project is not an Oracle
product, a complete enterprise landing zone or a compliance certification.
