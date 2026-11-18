locals {
  subject = "Allow group id ${var.developer_group_ocid}"
  # Resource types used by the minimal VCN foundation, including VCN defaults.
  # The operator can change/delete these network resources in this compartment.
  network_types = [
    "vcns", "subnets", "route-tables", "security-lists", "dhcp-options",
    "internet-gateways", "nat-gateways", "service-gateways"
  ]
  # Existing state/images must not become public through this bootstrap role.
  # Repository READ also permits image pulls; it is not metadata-only access.
  registry_permissions = ["REPOSITORY_CREATE", "REPOSITORY_READ", "REPOSITORY_INSPECT"]
  bucket_permissions   = ["BUCKET_CREATE", "BUCKET_READ", "BUCKET_INSPECT"]
  foundation_app = concat(
    [for kind in local.network_types : "${local.subject} to manage ${kind} in compartment id ${var.compartment_ocid}"],
    [for permission in local.registry_permissions : "${local.subject} to manage repos in compartment id ${var.compartment_ocid} where all {target.repo.name = '${var.registry_name}', request.permission = '${permission}'}"]
  )
  foundation_state = [for permission in local.bucket_permissions : "${local.subject} to manage buckets in compartment id ${var.state_compartment_ocid} where all {target.bucket.name = '${var.state_bucket_name}', request.permission = '${permission}'}"]
  observer_app = concat(
    [for kind in local.network_types : "${local.subject} to read ${kind} in compartment id ${var.compartment_ocid}"],
    [for kind in ["compute-container-family", "load-balancers", "metrics", "network-security-groups"] : "${local.subject} to read ${kind} in compartment id ${var.compartment_ocid}"],
    ["${local.subject} to inspect repos in compartment id ${var.compartment_ocid} where target.repo.name = '${var.registry_name}'"]
  )
  observer_state = ["${local.subject} to read buckets in compartment id ${var.state_compartment_ocid} where target.bucket.name = '${var.state_bucket_name}'"]
}

resource "oci_identity_policy" "application" {
  compartment_id = var.compartment_ocid
  name           = "${var.name}-${var.role}"
  description    = "Reviewed human operator access for a dedicated application boundary."
  statements     = var.role == "foundation-provisioner" ? local.foundation_app : local.observer_app
  lifecycle {
    precondition {
      condition     = var.compartment_ocid != var.state_compartment_ocid
      error_message = "Application and state compartments must be separate."
    }
    precondition {
      condition     = var.region == var.home_region
      error_message = "IAM policy writes must use the confirmed home region."
    }
  }
}

resource "oci_identity_policy" "state" {
  compartment_id = var.state_compartment_ocid
  name           = "${var.name}-${var.role}"
  description    = "Reviewed state-bucket metadata access; no object permissions."
  statements     = var.role == "foundation-provisioner" ? local.foundation_state : local.observer_state
  lifecycle {
    precondition {
      condition     = var.compartment_ocid != var.state_compartment_ocid
      error_message = "Application and state compartments must be separate."
    }
    precondition {
      condition     = var.region == var.home_region
      error_message = "IAM policy writes must use the confirmed home region."
    }
  }
}

output "access_review" {
  description = "Private review evidence. Terraform validation does not establish effective OCI permissions."
  value = {
    role                  = var.role
    application_policy_id = oci_identity_policy.application.id
    state_policy_id       = oci_identity_policy.state.id
    application_actions   = oci_identity_policy.application.statements
    state_actions         = oci_identity_policy.state.statements
    inherited_access      = "unknown-until-administrator-review-and-negative-tests"
    deployment_permission = "not-granted-by-this-template"
    state_object_access   = "not-granted-by-this-template"
  }
}
