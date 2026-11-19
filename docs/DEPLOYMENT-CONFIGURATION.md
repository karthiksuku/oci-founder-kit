# Prepare deployment configuration

`release configure` connects a selected environment to the existing native-state
and deployment gates. It creates local inputs only. It does not create credentials,
grant permissions, publish an image, initialize remote state or deploy resources.

Start after onboarding and foundation handoff, from the application directory:

```sh
python3 .oci-founder-kit/scripts/kit.py release configure --project . --environment rehearsal
```

The command lists missing choices together. It reuses the selected environment's
profile, region, compartments, networking, certificate, backend, port, health
route, image digest and sizing. An existing choice cannot be silently changed.
To retarget, use the separate backed-up environment workflow and recheck evidence.

Create a private mode-0600 JSON file with two sections:

| Section | Contents |
|---|---|
| `target` | Optional missing fields from the [environment schema](ENVIRONMENTS.md). Existing values must agree exactly. |
| `variables` | Required `tenancy_ocid`, `home_region`, `name`, `app_image`, `registry`, `allowed_ingress_cidrs`, `application_contract`. Optional `public_environment`, `secret_references`, `dependency_egress`. |

Variable shapes follow the [generic container example](../blueprints/web-container/terraform/terraform.tfvars.example).
`registry` contains the existing app compartment and exact repository name;
`app_image` must use that repository and the selected immutable digest.
`application_contract` records reviewed evidence for absent or disabled background
work. A supplied digest, architecture label or contract hash is configuration,
not independent verification of the image or application. Image publication and
runtime verification retain their existing gates.

Use explicit rehearsal ingress ranges. Keep secret **values** outside every input.
`secret_references` accepts Vault identifiers only; the app must implement and test
retrieval. Public environment settings enter Terraform state and OCI metadata.
The helper rejects common credential names and obvious credential-shaped values,
but heuristics cannot prove arbitrary text nonsecret: review every value.

```sh
python3 .oci-founder-kit/scripts/kit.py release configure --project . --environment rehearsal --config /private/deployment-choices.json
python3 .oci-founder-kit/scripts/kit.py release configure --project . --environment rehearsal --approve '<local-configuration-sha256>'
```

The first command saves a private review packet and returns its hash. Review its
actual target and variables before the second command. This local hash is never
a cloud approval. Proposals expire after one hour and are bound to the selected
environment, source, toolkit and reviewed infrastructure. Changed or interrupted
work must be inspected before a new proposal; partial output directories are not
adopted or overwritten.

Preparation writes owner-only `variables.json` and seven-field `backend.json`
under a new directory inside `.oci-kit/environments/NAME/`. It creates the
canonical empty OCI backend declaration only if absent, preserving an identical
existing declaration. It backs up the environment before binding missing choices.
The result returns the exact environment-specific `release init` command. Use the
returned variables path for the later `release plan --var-file` operation.
Initialization, planning with the remote backend, resource apply and cleanup each
retain their exact-plan approval boundary.

This path supports the reviewed generic `web-container` blueprint with separately
established runtime IAM (`manage_runtime_iam=false`). It refuses source hosting,
customized infrastructure and existing automatic Terraform variable files. Those
files are preserved; use the [manual workflow](WORKFLOW.md#review-and-deploy) when
they are intentional. Certificate issuance, DNS, hosted identity and inherited
state isolation remain prerequisites with their own review and evidence.

After deployment, inspect remaining acceptance work:

```sh
python3 .oci-founder-kit/scripts/kit.py architecture --project . --environment rehearsal
python3 .oci-founder-kit/scripts/kit.py journey --project . --environment rehearsal --kind build
```

Both reports are read-only and return a nonzero exit status while incomplete.
Missing live evidence cannot become a passing result through a saved preference.
