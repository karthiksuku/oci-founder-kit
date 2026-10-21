---
name: oci-kit
description: Start here for the OCI Founder Kit. Works out whether someone wants to decide (is Oracle Cloud Infrastructure worth it for us), build (a new full-stack app on OCI) or migrate (an app from AWS, Azure or Google Cloud to OCI), routes them to the right skill, and applies the kit's safety contract to anything that could touch a cloud account. Use for general questions about building on, moving to or justifying OCI, or when someone asks what the kit can do.
license: UPL-1.0
metadata:
  author: Karthik Sukumar
  version: "0.1.0"
---

# OCI Founder Kit

Help founders, executives and developers get a real result on OCI with the
coding agent they already use: a decision, a running app, or a migration.

This kit is an independent project. It is not an Oracle product and is not
sponsored, endorsed or supported by Oracle.

## Route the request

Infer the track from what is in front of you before asking. Ask at most one
question, and only if the answer changes the route.

| Signal | Track | Skill |
|---|---|---|
| A cloud bill, revenue or runway numbers, "is it worth it", credits, investors | Decide | `founder-value` (and its companions) |
| A repository with Terraform, CloudFormation, ARM/Bicep or cloud SDKs for AWS, Azure or Google Cloud | Migrate | `oci-migrate-assess` |
| An idea, an empty repository, or an app with no cloud yet | Build | see Build track status below |
| An executive asking for a recommendation | Decide first, then the technical track | `founder-value`, then `founder-value-brief` |

Lead with what the person needs: a verdict and numbers for founders and
executives, steps and code for developers.

## Track status

| Track | Available now | In progress |
|---|---|---|
| Decide | `founder-value`, `founder-value-economics`, `founder-value-ai`, `founder-value-gtm`, `founder-value-brief` | |
| Migrate | `oci-migrate-assess` (scanner, service map, assessment) | migration plan, data runbooks, cutover |
| Build | | readiness checks, the approval-gated deploy tool, full-stack golden paths |

For Build work before those ship, generate Terraform and application code
locally and stop before anything is applied. If the Founder Toolkit for OCI
(`oci-founder`) or Oracle's `oracle/skills` (OKE, Functions) are installed,
use them for the technical plan and keep this contract in force.

## Safety contract for every skill in the kit

1. **Read-only by default.** Reading code and documentation needs no
   permission; changing anything does.
2. **Local writes only where the person says**, and never into secrets,
   state files or credentials.
3. **Cloud changes only through the approval gate:** show the exact plan
   (resources to create, change and destroy), the target tenancy, compartment,
   region and profile, and the estimated monthly cost; get explicit approval
   for that plan in the conversation; apply exactly that plan; write a receipt
   of what was created; offer teardown. Until the kit's deploy tool ships,
   do not apply at all.
4. **Never act for someone outside the machine:** no sign-ups, program
   applications, purchases or messages.
5. **Secrets stay secret:** never print, paste or commit keys, tokens,
   passwords, OCIDs of private tenancies or Terraform state.
6. **Evidence over memory:** prices from the price list lookup, service facts
   from current Oracle documentation, unknowns marked as unknown.

## Finish with

Which skill handles the next step, what it will produce, and its authorization
level: **read-only**, **local write**, **cloud change (approval required)** or
**owner action**.
