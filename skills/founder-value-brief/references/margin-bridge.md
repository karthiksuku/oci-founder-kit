# Building the gross margin bridge

The bridge explains the margin change group by group, so a reader can see
which driver earns it and which assumption carries it.

## Method

Give every cost line in the scenario a `group` (compute, database, storage,
network, observability, or your own names), using the same group names on
both options. `value_model.py` then reports a bridge for the last month of
the horizon at list price:

```text
points for group g = (baseline cost of g - option cost of g) / revenue x 100
starting margin + sum(points) = option margin
```

The JSON result has it under `comparisons.<option>.margin_bridge`; the
Markdown report prints it as a table. Ungrouped lines appear as `other`, and
AI model cost is always `ai`. If one group dominates `other`, the grouping
needs another pass before the brief goes out.

## Presenting it

- Start from the baseline's durable margin, list the steps from the largest
  effect down, and end at the option's durable margin.
- Mark a step whose inputs are mostly `assumed` with a dagger and a footnote.
- If the `ai` step depends on a model change, say whether it has passed the
  evaluation gate.
- Keep credits out of the bridge; they belong in the credits section.
