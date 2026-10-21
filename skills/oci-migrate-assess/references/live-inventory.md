# Optional read-only inventory of the live account

Use only when the owner asks for it, with their own credentials, on their
machine. These commands list resources; they change nothing. Save the output
to a local file, outside Git, and compare it with the scan.

## AWS

```bash
aws resourcegroupstaggingapi get-resources --region <region> --output json > aws-resources.json
aws ce get-cost-and-usage --time-period Start=<yyyy-mm-01>,End=<yyyy-mm-01> \
  --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE > aws-costs.json
```

The tagging API lists most resource types, including untagged ones that
support tagging; run it per region in use.

## Azure

```bash
az resource list --output json > azure-resources.json
az consumption usage list --start-date <yyyy-mm-01> --end-date <yyyy-mm-dd> > azure-usage.json
```

## Google Cloud

```bash
gcloud asset search-all-resources --scope=projects/<project-id> --format=json > gcp-resources.json
```

Cloud Asset Inventory must be enabled on the project.

## Using the output

- Resources in the live list but not in code: add them to the assessment as
  "created outside code", with an owner.
- Resources in code but not live: likely unused modules or environments not
  deployed; confirm before planning them.
- The cost export feeds the `stated` current-cloud lines in
  `founder-value-economics`.
