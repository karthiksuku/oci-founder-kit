# Founder playbook

Six journeys, each with a prompt you can paste into Claude Code (`/skill`),
Codex (`$skill`) or Cursor. Every prompt asks the agent to draft and not to
act; keep that line when you adapt them.

## 1. "Is OCI worth it for us?" (ten minutes)

```text
/founder-value Is OCI worth it for us? Stage: <seed / Series A>. Customers:
<n>, growing <x>% a month, ARPA <amount>. Our monthly cloud bill by line is
below (or attached). Cash <amount>, monthly spend <amount>. Give me a
verdict, the two or three numbers that decide it, and one next step. Do not
sign up, apply or contact anyone.
```

You get Go, Pilot, Not now or Build here, with the deciding numbers or the
facts still missing.

## 2. The full value case (an hour, with your billing export)

```text
/founder-value Build a full value case for moving <workload> to OCI. Use our
billing export in ./billing/<file>. Price OCI from the public price list,
include our current credits (<amount>, expiring <date>), 2 months of dual
running and <n> engineering hours at <rate>. Write scenario.json, the model
report and value-case.md in ./work/. Planning only.
```

You get a scenario file you can re-run, the model report and a
`value-case.md` with a verdict, costs, the credit cliff and risks.

## 3. AI unit economics

```text
/founder-value-ai Our <feature> makes about <n> model calls per customer a
month, <in> input and <out> output tokens each, about <share>% cached input.
We pay <prices> per million tokens today. Compare the cost per call with two
or three models on OCI Generative AI, show AI share of ARPA for our plans and
the heavy-user cost, and tell me what evaluation we need before switching.
```

## 4. Credits and the cliff

```text
/founder-value-economics We expect <amount> of OCI credits for 12 months.
Show when they run out or expire, the monthly cash jump after that, how much
would expire unused, and what work we should pull forward to use them well.
```

## 5. Should we apply to the Startup Growth Engine?

```text
/founder-value-gtm Check our fit for the Oracle Startup Growth Engine. We are
incorporated in <country>, have <n> paying customers or pilots, and want to
run <workload> on OCI. List any blockers, then draft the application answers
from our value case with gaps marked. Do not submit anything.
```

## 6. The board brief

```text
/founder-value-brief Turn ./work/value-report.md into a one-page board brief:
the decision, a durable margin bridge, credits stated plainly, payback with
and without credits, and a risk register. Mark any assumed inputs.
```

## After the verdict

| Verdict | Next |
|---|---|
| Go | Hand the value case to `oci-founder` (Founder Toolkit for OCI) for the technical plan |
| Pilot | Run the one experiment the verdict names, with its threshold, stop date and cost ceiling |
| Not now | Note the condition that would change the answer and a date to recheck |
| Build here | Start with `oci-founder-start` for a minimal architecture |

## Good habits

- Keep real invoices, scenarios and reports in a `work/` folder outside Git
  (the repository's `.gitignore` already excludes it).
- Re-run the model when prices, usage or terms change; the facts file says
  when it was last checked.
- Compare the first three months of real OCI billing with the model and
  correct the scenario where it was wrong.
