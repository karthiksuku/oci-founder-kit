# Protected production verifier

Both the CLI and the Terraform apply gate require an independent signature. A founder's local checklist, unverified GitHub artifact, repository-controlled signing workflow or signed check with a different candidate binding cannot establish eligibility. After eligibility, the separate exact-plan approval is still required. A rollback to an older digest is also a new candidate and plan.

**Supported boundary.** Use a named production and rehearsal environment, distinct infrastructure/compartments/backend destinations, the identical tested image, and a clean committed project at its own Git root. Commit reviewed nonsecret app/kit installation inputs and ignore private state. For the generic web-container journey, select hosting-first migration and identify Next.js via the reviewed descriptor or the app’s Next.js package declaration. Other app profiles get diagnostics and cannot currently promote. The protected runner and its signing identity are deployment prerequisites; the kit never generates a production trust key, uploads evidence, runs arbitrary test adapters on a production machine, or enrolls itself.

1. In rehearsal test the candidate, preserve raw results privately, deploy through existing gates, and collect the current applied deployment receipt. Prepare the exact production plan. Request the private challenge with owner-only output (substitute the actual names and hash):

   ```sh
   umask 077
   .oci-founder-kit/scripts/oci-kit sre check --environment production \
     --rehearsal rehearsal --plan-sha256 "$PLAN_SHA" --json > "$PRIVATE/challenge.json"
   ```

   A blocked exit (3) is expected before signature. A valid challenge contains a `binding`: policy, project identity, Git revision, source fingerprint, kit hash, image digest, profile, critical journey identifier and canonical declaration hash (including all private assertions), production and rehearsal names and configuration hashes, rehearsal deployment receipt hash, exact pending production plan SHA. If no binding was emitted, resolve the named missing prerequisite. A missing private rehearsal journey blocks even the challenge. Changing its identifier or any assertion requires the verifier to retest and sign against the new challenge. The displayed verifier public key path is on the **production operator machine**, outside the checkout. Do not send the private plan, state or app credentials to a PR job.

2. Enroll an independently controlled **Ed25519 public key** at `/etc/oci-founder-kit/sre-verifiers/<project-identity>/<production-environment>.pub` on that machine through an authorized administrator. Use a single OpenSSH public key line. All directories and the file must be root owned, with no group/world write or symlinks. The private key remains exclusively with a protected release verifier. A new checkout identity needs deliberate re-enrollment. Rotate or revoke access by replacing or removing the enrolled key. No workspace or environment override grants trust.

3. A protected coordinator must independently authenticate the repository, reviewed workflow version, candidate commit, digest and plan binding before collecting evidence. The verifier securely obtains the exact private journey declaration, recomputes its canonical SHA-256, and checks every declared assertion in the selected browser journey before reporting main-action success. The declaration text never appears in a challenge or public log. Use a protected ref/workflow and read-only, isolated jobs for candidate code, with **no access to the signing key**. A separate signing job must use reviewed verifier code and private artifacts fetched from specifically authenticated successful runs, never run a PR's test code in the signer, and never sign unchecked artifacts received from an app or from arbitrary pull requests. Local reports are inputs for investigation; generating a signature does not make a test happen.

   The shipped protected-runner adapter reads one dedicated JUnit suite per control. Match each required assertion in the policy to a named testcase; retain actual framework output and use an independent runner that confirms the commit, digest and rehearsal target. For `restore`, add source-measured JUnit properties `recovery_seconds` and `data_age_seconds`. Failed, missing, skipped or duplicate required cases block assembly. For the two scanner controls the adapter reads the kit's actual redacted JSON and recomputes the policy result. Example (repeat per control in an authenticated verifier job, selecting artifacts from that specific successful run):

   ```sh
   python3 "$KIT/scripts/sre_results.py" --challenge "$PRIVATE/challenge.json" \
     --control browser_journey --artifact "$PRIVATE/run/browser.junit.xml" \
     --observed-at "$ACTUAL_RUN_EPOCH" --out-dir "$PRIVATE/verified-results"
   ```

   The out directory must already exist, mode 0700. Keep individual inputs mode 0600. The adapter never executes candidate code and never accepts a check status from the agent's narrative. It cannot authenticate a JUnit producer: selecting trusted runs and verifying their build/target identity is the protected coordinator's responsibility. GitHub branch protection alone does not authenticate a copied local file.

   For a custom verifier producing the same interface: For each control listed in the challenge, it retains `<control>.artifact` (exact raw result, 1 byte–16 MiB, private) and produces `<control>.json` (owner-only; at most 1 MiB). It derives observations from actual test output; adapters must not assume "all true" from exit code alone. Each control record has exactly:

   - `schema`: `oci-sre-control/1`; `id`: the control identifier.
   - `binding_sha256`: SHA-256 of the canonical challenge binding (Python `json.dumps(binding, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()`).
   - `observed_at`: integer UTC epoch seconds for the check itself; `raw_artifact_sha256`: SHA-256 of the unmodified raw result.
   - `observations`: the named checks in [the versioned policy](../scripts/sre_gate.py). Booleans refer to independently verified outcomes; false, missing, malformed or stale means no promotion. For restore include actual nonnegative `recovery_seconds` and `data_age_seconds` measured on the isolated restore. For `security_scan` and `oci_registry_scan` supply the full redacted [scan result](../scripts/sre_scan.py); the gate recomputes severity, coverage, identity and freshness rather than trusting a `passed` field. If optional lower-priority findings exist, maintain the owner's dated remediation queue. Capture historical run artifacts for incident investigation. All mandatory control results have a 24-hour maximum age for promotion; publication of a new attestation cannot refresh old observations.

4. In the isolated protected verifier, assemble the report from real artifacts. The challenge data and observations are not secret keys, but remain private. Set `KIT` to a reviewed kit checkout pinned independently of the candidate.

   ```sh
   python3 "$KIT/scripts/sre_gate.py" --challenge "$PRIVATE/challenge.json" \
     --report-dir "$PRIVATE/verified-results" --out "$PRIVATE/sre-$PLAN_SHA.json"
   ssh-keygen -Y sign -f "$PROTECTED_SIGNING_KEY" -n oci-founder-production-v1 "$PRIVATE/sre-$PLAN_SHA.json"
   ```

   The first command refuses to assemble missing controls, mismatched results/artifacts or already-failed checks, and never signs. The resulting versioned packet contains `schema` (`oci-sre-attestation/1`), `issued_at`, exact `binding` and `controls`. Each control contains `observations`, `observed_at`, and `artifact_sha256`. SSH signs the exact file bytes, including its trailing newline.

5. The operator imports the exact JSON and its detached SSH signature into the chosen production environment's private evidence directory, using the names below (`ssh-keygen` adds `.sig` after `.json`; rename on import). Do not overwrite an in-flight reviewed packet; process only the intended hash.

   ```sh
   install -m 600 "$PRIVATE/sre-$PLAN_SHA.json" ".oci-kit/environments/production/evidence/sre-$PLAN_SHA.json"
   install -m 600 "$PRIVATE/sre-$PLAN_SHA.json.sig" ".oci-kit/environments/production/evidence/sre-$PLAN_SHA.sig"
   .oci-founder-kit/scripts/oci-kit sre check --environment production --rehearsal rehearsal --plan-sha256 "$PLAN_SHA"
   ```

   The gate recomputes the current plan hash, source/revision, receipt/configuration bindings, signature and control results. It rechecks again before the Terraform apply subprocess. It never trusts a saved eligibility result or automatically approves any cloud action. Legitimate non-workload bootstrap and separately reviewed destroy plans retain their existing approval policy. Unbound Container Instance workload applies require migration into a named environment first. This is an in-kit safeguard; the operator must separately restrict direct OCI and Terraform access.

The implementation assumes trusted OS, installed kit, verifier and administration. The signature proves which enrolled verifier issued the explicit observations, not that arbitrary external CI or a self-operated signer was configured safely. A signed packet alone does not establish an SLO over a month, third-party assurance or production availability.
