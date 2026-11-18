mock_provider "oci" {}

variables {
  tenancy_ocid           = "ocid1.tenancy.oc1..synthetictenancy"
  compartment_ocid       = "ocid1.compartment.oc1..syntheticapp"
  state_compartment_ocid = "ocid1.compartment.oc1..syntheticstate"
  developer_group_ocid   = "ocid1.group.oc1..syntheticdevelopers"
  role                   = "foundation-provisioner"
  name                   = "founder-rehearsal"
  registry_name          = "founder-rehearsal"
  state_bucket_name      = "founder-rehearsal-state"
  region                 = "us-phoenix-1"
  home_region            = "us-phoenix-1"
  config_file_profile    = "SYNTHETIC"
  auth                   = "SecurityToken"
}

run "foundation_grants_are_bounded" {
  command = plan
  assert {
    condition     = length(oci_identity_policy.application.statements) == 11 && length(oci_identity_policy.state.statements) == 3
    error_message = "Review every additional grant before extending this role."
  }
  assert {
    condition     = oci_identity_policy.application.compartment_id == var.compartment_ocid && oci_identity_policy.state.compartment_id == var.state_compartment_ocid
    error_message = "Each policy must attach to its own target, not a sibling or tenancy root."
  }
  assert {
    condition     = alltrue([for statement in oci_identity_policy.application.statements : startswith(statement, "Allow group id ${var.developer_group_ocid} to ") && strcontains(statement, " in compartment id ${var.compartment_ocid}") && !strcontains(statement, var.state_compartment_ocid)])
    error_message = "Application grants must use exactly the selected group and app boundary."
  }
  assert {
    condition     = alltrue([for statement in oci_identity_policy.state.statements : startswith(statement, "Allow group id ${var.developer_group_ocid} to manage buckets in compartment id ${var.state_compartment_ocid} where all {target.bucket.name = '${var.state_bucket_name}', request.permission = '")])
    error_message = "Every state grant must be exact bucket metadata, not objects or a sibling."
  }
  assert {
    condition     = alltrue([for permission in ["BUCKET_CREATE", "BUCKET_READ", "BUCKET_INSPECT"] : contains(oci_identity_policy.state.statements, "Allow group id ${var.developer_group_ocid} to manage buckets in compartment id ${var.state_compartment_ocid} where all {target.bucket.name = '${var.state_bucket_name}', request.permission = '${permission}'}")])
    error_message = "State grants must match the reviewed permission allowlist exactly."
  }
  assert {
    condition     = alltrue([for permission in ["REPOSITORY_CREATE", "REPOSITORY_READ", "REPOSITORY_INSPECT"] : contains(oci_identity_policy.application.statements, "Allow group id ${var.developer_group_ocid} to manage repos in compartment id ${var.compartment_ocid} where all {target.repo.name = '${var.registry_name}', request.permission = '${permission}'}")])
    error_message = "Registry grants must match the exact repository and permission allowlist."
  }
  assert {
    condition     = alltrue([for kind in ["vcns", "subnets", "route-tables", "security-lists", "dhcp-options", "internet-gateways", "nat-gateways", "service-gateways"] : contains(oci_identity_policy.application.statements, "Allow group id ${var.developer_group_ocid} to manage ${kind} in compartment id ${var.compartment_ocid}")])
    error_message = "Networking access must match the reviewed service resource types."
  }
  assert {
    condition     = alltrue([for statement in concat(oci_identity_policy.application.statements, oci_identity_policy.state.statements) : !strcontains(statement, " in tenancy") && !strcontains(statement, "all-resources") && !strcontains(statement, "objects") && !strcontains(statement, "PAR_MANAGE") && !strcontains(statement, "BUCKET_DELETE") && !strcontains(statement, "BUCKET_UPDATE") && !strcontains(statement, "REPOSITORY_DELETE") && !strcontains(statement, "REPOSITORY_UPDATE") && !strcontains(statement, "REPOSITORY_MANAGE") && !strcontains(statement, "secret") && !strcontains(statement, "manage policies")])
    error_message = "This role must not gain state data, public-access updates, image publication/deletion, secrets or tenancy administration."
  }
}

run "observer_has_no_mutation_grants" {
  command = plan
  variables { role = "observer" }
  assert {
    condition     = length(oci_identity_policy.application.statements) == 13 && length(oci_identity_policy.state.statements) == 1
    error_message = "Review observer grant changes."
  }
  assert {
    condition     = alltrue([for statement in concat(oci_identity_policy.application.statements, oci_identity_policy.state.statements) : !strcontains(statement, " to manage ") && !strcontains(statement, " to use ") && !strcontains(statement, " in tenancy") && !strcontains(statement, "objects") && !strcontains(statement, "secret") && !strcontains(statement, "log")])
    error_message = "Observer must not gain mutation, data-object, secret or raw-log access."
  }
  assert {
    condition     = one(oci_identity_policy.state.statements) == "Allow group id ${var.developer_group_ocid} to read buckets in compartment id ${var.state_compartment_ocid} where target.bucket.name = '${var.state_bucket_name}'"
    error_message = "Observer state access must remain metadata for exactly one bucket."
  }
  assert {
    condition     = output.access_review.deployment_permission == "not-granted-by-this-template" && output.access_review.state_object_access == "not-granted-by-this-template"
    error_message = "Local plans must not assert deployment or state-data authorization."
  }
}

run "reject_tenancy_as_application" {
  command = plan
  variables { compartment_ocid = "ocid1.tenancy.oc1..synthetictenancy" }
  expect_failures = [var.compartment_ocid]
}

run "reject_tenancy_as_state" {
  command = plan
  variables { state_compartment_ocid = "ocid1.tenancy.oc1..synthetictenancy" }
  expect_failures = [var.state_compartment_ocid]
}

run "reject_shared_app_state" {
  command = plan
  variables { state_compartment_ocid = "ocid1.compartment.oc1..syntheticapp" }
  expect_failures = [oci_identity_policy.application, oci_identity_policy.state]
}

run "reject_wrong_home_region" {
  command = plan
  variables { region = "uk-london-1" }
  expect_failures = [oci_identity_policy.application, oci_identity_policy.state]
}

run "reject_user_as_group" {
  command = plan
  variables { developer_group_ocid = "ocid1.user.oc1..syntheticuser" }
  expect_failures = [var.developer_group_ocid]
}

run "reject_wildcard_repository" {
  command = plan
  variables { registry_name = "founder-*" }
  expect_failures = [var.registry_name]
}

run "reject_bucket_policy_injection" {
  command = plan
  variables { state_bucket_name = "bucket', request.permission = 'OBJECT_READ" }
  expect_failures = [var.state_bucket_name]
}

run "reject_unsupported_role" {
  command = plan
  variables { role = "administrator" }
  expect_failures = [var.role]
}

run "reject_implicit_auth" {
  command = plan
  variables { auth = "" }
  expect_failures = [var.auth]
}
