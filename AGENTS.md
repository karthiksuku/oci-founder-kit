# Working on this repository

The kit has three tracks: Decide (`founder-value*` skills), Build (`oci-*`
build and deploy skills) and Migrate (`oci-migrate-*` skills). See
`docs/ROADMAP.md` for what exists and the evidence each piece needs.

## Cloud safety

- Never run `terraform apply`, `terraform destroy` or any OCI write outside
  the approval-gated deploy tool, and never without the owner approving that
  exact plan in the current conversation.
- Live tests run only in a sandbox compartment named by the owner, and every
  live run ends with a teardown and a check that nothing is left running.
- No credentials, private keys, OCIDs of real tenancies, Terraform state or
  plan files in Git. Receipts committed as evidence are redacted first.
- Name AWS, Azure and Google Cloud factually as migration sources or public
  design references. Attribute references, check their licenses and distinguish
  reviewed source from behavior independently verified by this kit.

## Conventions

- The migration service map is `skills/oci-migrate-assess/assets/service-map.json`.
  Every change must pass `tests/test_service_map.py`, which checks Terraform
  types against provider schemas in `tests/fixtures/provider-types/`. Refresh
  those with `python3 scripts/refresh_provider_types.py` when providers move.
- Skills live in `skills/<name>/SKILL.md` with references beside them. Keep
  frontmatter to the portable keys (`name`, `description`, `license`,
  `compatibility`, `metadata`, `allowed-tools`) and keep `metadata.version`
  equal to the manifests' version.
- The calculator and price lookup are standard-library Python in
  `skills/founder-value/scripts/`. Change behaviour test-first in `tests/`.
- Never type an OCI price into a skill, reference or example. Fill prices
  with `price_lookup.py` so they carry a part number and date.
- Time-sensitive program facts belong in
  `skills/founder-value/references/facts.md` with a source and a checked date.
- Credits, introductions, co-selling and Marketplace publication are at
  Oracle's discretion; never write them as promises.
- Before committing run:
  `python3 scripts/validate.py && python3 -m unittest discover -s tests && claude plugin validate .`
- After changing the template or the model, regenerate the example:
  `python3 skills/founder-value/scripts/price_lookup.py fill skills/founder-value/assets/scenario.template.json --out skills/founder-value/assets/scenario.example.json`
  then `python3 skills/founder-value/scripts/value_model.py skills/founder-value/assets/scenario.example.json --out examples/seed-ai-saas/value-report.md`,
  and update any numbers quoted in the README and docs.
