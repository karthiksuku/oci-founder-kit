# What will my app cost?

In the installed app, ask Claude Code or Codex: **“Show the 24-hour demo cost, the cost of running for 30 days, and what will keep costing money after cleanup. Explain the largest unknown.”**

```sh
.oci-founder-kit/scripts/oci-kit cost preview --environment rehearsal
```

This offline preview covers a named rehearsal or production using the web-container blueprint. It checks the attached Terraform against the reviewed source and reads the environment's configured OCPUs and memory. The default footprint includes one E4 Container Instance and one 10 Mbps flexible HTTPS load balancer. If a shape choice or matching infrastructure is missing, the affected quantity stays unknown. The operational estimate assumes continuous operation for exactly 24 or 720 hours. Before approving deployment, compare the pending Terraform plan with these modeled quantities and review unmodeled components, usage, taxes, support and commercial terms.

Each line in the JSON report gives the modeled quantity, Oracle SKU, billing unit, list rate, source-check date and rate basis. For the tiered load balancer, the illustration uses the highest listed tier because the kit cannot determine how much of a shared allowance is available. The public USD PAY_AS_YOU_GO snapshot is usable for 30 days from its check date. Compare with your region and agreement before approval. [Oracle Container Instances and load balancer prices](https://www.oracle.com/cloud/price-list/)

**Try it with a small footprint.** For an existing web-container environment configured with one OCPU and 2 GB of memory, the 24-hour demo includes 24 OCPU-hours, 48 GB-hours, 24 load balancer hours and 240 Mbps-hours. The 30-day quantities are 720, 1,440, 720 and 7,200 respectively. The CLI calculates the USD subtotal from its dated rates. Database, storage, transfer and other unreviewed costs remain visible as unknown. A known subtotal alone cannot establish the total bill.

## Fill the gaps once

Use a local, private working directory outside your app. These optional files can contain business-sensitive assumptions. A preview with incomplete inputs still prints its report.

```sh
umask 077
private_cost_dir=$(mktemp -d)
kit=.oci-founder-kit/scripts/oci-kit
cp .oci-founder-kit/recipes/launch-cost/rates.json "$private_cost_dir/rates.json"
"$kit" cost preview --environment rehearsal --rates "$private_cost_dir/rates.json" --json > "$private_cost_dir/preview.json" || test "$?" -eq 3
python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["assumptions_template"], indent=2))' \
  < "$private_cost_dir/preview.json" > "$private_cost_dir/assumptions.json"
```

Edit the template with dated estimates from the current configuration, your provider bills and the exact proposed plan. Use USD, counting each charge once. For each additional category enter the expected total for the demo and for 30 days of operation. Include all retained external identity, database and storage charges. During a hosting migration, put temporary source-hosting overlap in its own category. Capture shared networking, DNS, security and foundation services under **other** where applicable. Count only resources paid for by this project under the allocation you agreed. Use an explicit zero for a category reviewed as inapplicable. Leave unknown figures as `null`.

For each category, including compute and the load balancer, enter how many billable resources you expect to keep after the proposed cleanup and their estimated **combined cost for the following 30 days**. Use equivalent units when comparing counts before and after. An object or image count is distinct from billable bytes.

If the included rates have expired, refresh your private copy before saving the forecast. Inspect the lookup's exit status and any refused parts. This explicit lookup contacts Oracle's public catalogue using part numbers and USD only.

```sh
python3 .oci-founder-kit/skills/founder-value/scripts/price_lookup.py fill \
  .oci-founder-kit/recipes/launch-cost/rates.template.json --out "$private_cost_dir/rates.json"
```

Save the exact estimates, assumptions and dated rates used for this decision.

```sh
"$kit" cost preview --environment rehearsal --rates "$private_cost_dir/rates.json" \
  --assumptions "$private_cost_dir/assumptions.json" --json > "$private_cost_dir/before.json" || test "$?" -eq 3
```

## Compare after approved cleanup

Keep the before report, original assumptions, rates and local environment. After a separately approved cleanup, inspect the actual remaining resources, versions, backups, images and shared services. Preserve the private inventory and supporting service evidence. List invisible resources as unknown when access is denied or inventory is incomplete. [Teardown verification and Usage API](OPERATIONS.md#cleanup)

```sh
python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["cleanup_template"], indent=2))' \
  < "$private_cost_dir/before.json" > "$private_cost_dir/after.json"
```

Set `as_of` to the inventory date and `inventory_evidence_sha256` to the SHA-256 of the private evidence you reviewed. For every reviewed category, enter the **observed count** and **repriced combined cost for the next 30 days**. The template binds this comparison to the original estimate. Correcting the scope, target or quantities requires a new comparison.

```sh
"$kit" cost preview --environment rehearsal --rates "$private_cost_dir/rates.json" \
  --assumptions "$private_cost_dir/assumptions.json" --after-cleanup "$private_cost_dir/after.json"
```

The JSON includes per-category count and cost differences. A later comparison reconstructs the forecast using its original date and labels it historical. Supply the same rate and assumptions files that produced the before report. Record a fresh inventory date and verify the actual remaining resources first. Each new figure remains an owner-reviewed inventory estimate. The preview separately displays any current, receipt-matched Usage API observation for the web component and its actual billing period and currency. Reporting can lag and can cover only a subset of resources. Unavailable billing stays unknown. OCI budget alerts are soft thresholds evaluated approximately every 24 hours. [Oracle Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm)
