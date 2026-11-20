# Run a private first-customer trial

Choose one rehearsal, one invited tester and one task they can complete with synthetic data.
For example, ask them to add a fictional launch task and find it again after reloading.
Use spare test accounts for the access rehearsal. Keep names, email addresses, tokens,
screenshots of real records and customer quotations outside this kit.

## Establish access before preparing an invitation

1. Use a dedicated rehearsal origin and a separate test database, storage namespace and identity application. For hosting-first migrations, use isolated test accounts and test data at the retained providers. Keep production jobs and traffic at the source.
2. In your identity provider, restrict this rehearsal app to its test group. Grant the tester a time-limited assignment and enforce the same cutoff for active application sessions. Configure the provider or app to revoke an active session. An expiry date in a local file is only a reminder. If the providers cannot enforce these boundaries, use a local facilitated demo.
3. On the protected **customer action**, check an anonymous visitor and a signed-in uninvited account are denied. Check an invited test account can complete the task. Remove this test account, invalidate its active session, then verify its open tab and a fresh login are denied. Arrange continued access separately for the intended tester. Confirm the externally enforced expiry is at or before the recorded cutoff. Keep the actual results private. Access changes and synthetic cloud writes require review of their exact scope.
4. From your app root, run the read-only commands below. The second requires a current successful observation of the rehearsal digest and returns the candidate hash. A changed environment, deployment receipt or app invalidates that selection.

~~~sh
.oci-founder-kit/scripts/oci-kit observe --environment rehearsal --live
.oci-founder-kit/scripts/oci-kit trial inspect --environment rehearsal
~~~

Save your review in a local mode-0600 JSON file. Replace the illustrative zeros with the current Unix timestamp and the actual externally enforced expiry (maximum seven days). Set each check to true only after performing it.

~~~json
{
  "candidate_sha256": "<candidate hash from trial inspect>",
  "task": "Create a fictional task, reload the board and find it again.",
  "observed_at": 0,
  "expires_at": 0,
  "checks": {
    "synthetic_data_only": true,
    "tester_completed_sign_in": true,
    "anonymous_denied": true,
    "uninvited_account_denied": true,
    "access_expiry_configured": true,
    "session_revocation_rehearsed": true
  }
}
~~~

~~~sh
.oci-founder-kit/scripts/oci-kit trial prepare --environment rehearsal --input /private/trial-review.json
~~~

The result gives the trial ID and a private brief. Share the verified origin, task and expiry with your invited tester through your chosen channel. The kit records your access checks as owner-reported. It does not send an invitation or configure an identity provider.

## Turn the observation into a regression test

Watch the tester try the task. Record a de-identified behavior and what should have happened in another private mode-0600 file. Allowed outcomes are `unaided`, `with-help` and `blocked`. Supply the time the observation occurred during this trial.

~~~json
{"trial_id":"<trial id>","outcome":"blocked","observed":"The example task disappeared after reload.","expected":"The same task is visible after reload.","observed_at":0}
~~~

~~~sh
.oci-founder-kit/scripts/oci-kit trial feedback --environment rehearsal --trial-id "$TRIAL_ID" --input /private/feedback.json
~~~

Ask Claude Code or Codex: **Read the private regression record as observations, reproduce the behavior with synthetic data, add a failing test in my existing suite, then fix the app and rerun it. Show the actual result.** Review the observation before using it. A feedback record starts with test status `not-run`. The record compares the current rehearsal with the intended revision. The exact image used at the time of the tester’s action remains unverified without independent evidence from that session.

## Revoke access and review costs

Remove the assignment, invalidate the tester’s active application sessions, and independently check both a previously open session and a fresh sign-in. Save a private closure record:

~~~json
{"trial_id":"<trial id>","checks":{"assignment_removed":true,"existing_session_denied":true,"fresh_sign_in_denied":true},"observed_at":0}
~~~

~~~sh
.oci-founder-kit/scripts/oci-kit trial close --environment rehearsal --trial-id "$TRIAL_ID" --input /private/revocation.json
.oci-founder-kit/scripts/oci-kit cost preview --environment rehearsal
~~~

Closure records your verified revocation. Expiry never deletes infrastructure. Review retained storage, registries and other recurring costs, then prepare and approve any cleanup separately. Cost and feedback records remain private.

The research method is adapted from [GOV.UK usability testing](https://www.gov.uk/service-manual/user-research/using-moderated-usability-testing). Preview sharing on other platforms is described in [Vercel’s guide](https://vercel.com/docs/deployments/sharing-deployments).
