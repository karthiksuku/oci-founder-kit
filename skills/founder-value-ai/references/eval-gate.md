# Evaluation gate for a model change

A model change counts as a saving only after this gate passes. Until then,
report the saving as a hypothesis and keep the verdict at Pilot.

## Before the test

- **Task set.** 50 to 200 real tasks from the product, sampled across user
  segments, with personal data removed or the founder's approval to use it.
- **Quality measure.** What "good" means for the feature: exact match, a
  rubric scored by a person, a rubric scored by a model and spot-checked, or
  a product metric such as acceptance rate.
- **Pass threshold.** Set it before running, relative to the current model,
  for example "no worse than 2 points below the current model on the rubric
  and no new failure category".
- **Latency limit.** p95 time to first token and to completion that the
  product can accept.
- **Cost ceiling** for the test itself.

## Running it

- Same prompts, same context, same temperature where possible.
- Record cost per action, quality score, failures by category and latency.
- Keep the outputs; a reviewer should be able to check any score.

## Deciding

| Result | Verdict |
|---|---|
| Passes quality and latency | The saving is real for this feature; move to a staged rollout |
| Passes for some task types only | Tier: route those task types to the cheaper model |
| Fails | Keep the current model for this feature; look at prompt and cache levers instead |

Write the result into the value case with the date, the model and the task
set size. Re-run the gate when the product's tasks change materially.
