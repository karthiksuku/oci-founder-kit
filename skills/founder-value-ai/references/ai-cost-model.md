# AI cost model

## Cost per action

```text
uncached_in = input_tokens x (1 - cached_share)
cached_in   = input_tokens x cached_share
cost/action = (uncached_in x input_price + cached_in x cached_price
               + output_tokens x output_price) / 1,000,000
```

Prices are per 1,000,000 tokens. If a model has no cached-input price, the
calculator charges cached tokens at the input price. Long-context tiers can
have higher prices; if the product sends prompts above the tier boundary,
use the long-context parts.

## Per customer and per plan

```text
AI cost per customer = cost/action x actions per customer per month
AI share of ARPA     = AI cost per customer / ARPA
AI gross margin      = (plan price - AI cost - other COGS per customer) / plan price
```

Run it for the median user and for a heavy user (p90 or p95 of actions).
Flat-priced plans usually lose money on the heavy tail first.

## Levers, in the order to try them

1. **Prompt and context trimming.** Fewer input tokens per action. Free to
   try; measure quality.
2. **Caching.** A higher cached share for repeated system prompts and
   context. Check the model's cached-input price.
3. **Tiering.** Route easy actions to a smaller model:
   ```text
   blended cost/action = share_small x cost_small + (1 - share_small) x cost_large
   ```
   Model each model as an option, then combine by hand, or run the scenario
   with the blended per-token prices as stated inputs.
4. **Model change.** A different provider's model on OCI Generative AI.
   Requires the evaluation gate.
5. **Dedicated capacity.** For steady high volume.
   ```text
   dedicated monthly    = AI units x price per unit hour x 744
   on-demand monthly    = monthly actions x cost/action
   breakeven actions    = dedicated monthly / cost/action
   ```
   Only valid when the units can carry the volume at the latency the product
   needs. Confirm throughput before using the breakeven.

## Packaging the feature

- Set a ceiling for AI share of ARPA the founder will accept, and design
  plans so the median and heavy user stay under it.
- Use fair-use limits, usage-based add-ons or credit packs where heavy users
  would break margin.
- Re-run the model when token counts change; new features tend to grow
  context length.

## Pricing metrics you will see in the price list

| Metric | Meaning | Kit behaviour |
|---|---|---|
| `1,000,000 Tokens` | Per-token pricing; separate parts for input, cached input and output | Auto-filled |
| `10,000 Transactions` | For some models a transaction is a character | Not auto-filled; measure characters |
| `AI Unit Per Hour` | Dedicated capacity | Use the dedicated formula above |
| `1000 Requests`, `1000 Search Units`, `Image` | Tools such as search, rerank, image generation | Add as ordinary cost lines |
