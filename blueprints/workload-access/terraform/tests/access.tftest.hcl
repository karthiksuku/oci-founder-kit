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
    condition     = length(oci_identity_policy.application[0].statements) == 11 && length(oci_identity_policy.state[0].statements) == 3
    error_message = "Review every additional grant before extending this role."
  }
  assert {
    condition     = oci_identity_policy.application[0].compartment_id == var.compartment_ocid && oci_identity_policy.state[0].compartment_id == var.state_compartment_ocid
    error_message = "Each policy must attach to its own target, not a sibling or tenancy root."
  }
  assert {
    condition     = alltrue([for statement in oci_identity_policy.application[0].statements : startswith(statement, "Allow group id ${var.developer_group_ocid} to ") && strcontains(statement, " in compartment id ${var.compartment_ocid}") && !strcontains(statement, var.state_compartment_ocid)])
    error_message = "Application grants must use exactly the selected group and app boundary."
  }
  assert {
    condition     = alltrue([for statement in oci_identity_policy.state[0].statements : startswith(statement, "Allow group id ${var.developer_group_ocid} to manage buckets in compartment id ${var.state_compartment_ocid} where all {target.bucket.name = '${var.state_bucket_name}', request.permission = '")])
    error_message = "Every state grant must be exact bucket metadata, not objects or a sibling."
  }
  assert {
    condition     = alltrue([for permission in ["BUCKET_CREATE", "BUCKET_READ", "BUCKET_INSPECT"] : contains(oci_identity_policy.state[0].statements, "Allow group id ${var.developer_group_ocid} to manage buckets in compartment id ${var.state_compartment_ocid} where all {target.bucket.name = '${var.state_bucket_name}', request.permission = '${permission}'}")])
    error_message = "State grants must match the reviewed permission allowlist exactly."
  }
  assert {
    condition     = alltrue([for permission in ["REPOSITORY_CREATE", "REPOSITORY_READ", "REPOSITORY_INSPECT"] : contains(oci_identity_policy.application[0].statements, "Allow group id ${var.developer_group_ocid} to manage repos in compartment id ${var.compartment_ocid} where all {target.repo.name = '${var.registry_name}', request.permission = '${permission}'}")])
    error_message = "Registry grants must match the exact repository and permission allowlist."
  }
  assert {
    condition     = alltrue([for kind in ["vcns", "subnets", "route-tables", "security-lists", "dhcp-options", "internet-gateways", "nat-gateways", "service-gateways"] : contains(oci_identity_policy.application[0].statements, "Allow group id ${var.developer_group_ocid} to manage ${kind} in compartment id ${var.compartment_ocid}")])
    error_message = "Networking access must match the reviewed service resource types."
  }
  assert {
    condition     = alltrue([for statement in concat(oci_identity_policy.application[0].statements, oci_identity_policy.state[0].statements) : !strcontains(statement, " in tenancy") && !strcontains(statement, "all-resources") && !strcontains(statement, "objects") && !strcontains(statement, "PAR_MANAGE") && !strcontains(statement, "BUCKET_DELETE") && !strcontains(statement, "BUCKET_UPDATE") && !strcontains(statement, "REPOSITORY_DELETE") && !strcontains(statement, "REPOSITORY_UPDATE") && !strcontains(statement, "REPOSITORY_MANAGE") && !strcontains(statement, "secret") && !strcontains(statement, "manage policies")])
    error_message = "This role must not gain state data, public-access updates, image publication/deletion, secrets or tenancy administration."
  }
}

run "observer_has_no_mutation_grants" {
  command = plan
  variables { role = "observer" }
  assert {
    condition     = length(oci_identity_policy.application[0].statements) == 13 && length(oci_identity_policy.state[0].statements) == 1
    error_message = "Review observer grant changes."
  }
  assert {
    condition     = alltrue([for statement in concat(oci_identity_policy.application[0].statements, oci_identity_policy.state[0].statements) : !strcontains(statement, " to manage ") && !strcontains(statement, " to use ") && !strcontains(statement, " in tenancy") && !strcontains(statement, "objects") && !strcontains(statement, "secret") && !strcontains(statement, "log")])
    error_message = "Observer must not gain mutation, data-object, secret or raw-log access."
  }
  assert {
    condition     = one(oci_identity_policy.state[0].statements) == "Allow group id ${var.developer_group_ocid} to read buckets in compartment id ${var.state_compartment_ocid} where target.bucket.name = '${var.state_bucket_name}'"
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

run "app_deployer_has_no_state_or_admin_grants" {
  command = plan
  variables {
    role             = "app-deployer"
    certificate_ocid = "ocid1.certificate.oc1.phx.syntheticcertificate"
  }
  assert {
    condition     = length(oci_identity_policy.application) == 1 && length(oci_identity_policy.state) == 0
    error_message = "App deployment must not create a state policy."
  }
  assert {
    condition     = length(oci_identity_policy.application[0].statements) == 13
    error_message = "Review all deployment statement changes."
  }
  assert {
    condition     = alltrue([for statement in oci_identity_policy.application[0].statements : !strcontains(statement, " in tenancy") && !strcontains(statement, "MOVE") && !strcontains(statement, "LOG_RETRIEVE") && !strcontains(statement, "secret") && !strcontains(statement, "manage policies") && !strcontains(statement, "CERTIFICATE_UPDATE") && !strcontains(statement, "WITH_PRIVATE_KEY")])
    error_message = "App operator must not gain admin, movement, raw logs, secrets or certificate-key reads."
  }
  assert {
    condition     = contains(oci_identity_policy.application[0].statements, "Allow group id ${var.developer_group_ocid} to use subnets in compartment id ${var.compartment_ocid}") && anytrue([for statement in oci_identity_policy.application[0].statements : strcontains(statement, "VCN_ATTACH") && strcontains(statement, "VCN_DETACH") && !strcontains(statement, "VCN_DELETE")])
    error_message = "Existing networking dependencies need attachment permissions, not VCN deletion."
  }
  assert {
    condition     = alltrue([for statement in oci_identity_policy.application[0].statements : !strcontains(statement, "certificate") || strcontains(statement, "target.leaf-certificate.id = '${var.certificate_ocid}'")])
    error_message = "Certificate access must select exactly the reviewed certificate."
  }
}

run "state_operator_exact_objects_and_no_version_deletion" {
  command = plan
  variables {
    role      = "state-operator"
    state_key = "rehearsal/app.tfstate"
  }
  assert {
    condition     = length(oci_identity_policy.application) == 0 && length(oci_identity_policy.state) == 1 && length(oci_identity_policy.state[0].statements) == 10
    error_message = "State operator must create only its ten reviewed state statements."
  }
  assert {
    condition     = alltrue([for statement in oci_identity_policy.state[0].statements : strcontains(statement, "target.bucket.name = '${var.state_bucket_name}'") && !strcontains(statement, "OBJECT_VERSION_DELETE") && !strcontains(statement, "BUCKET_UPDATE") && !strcontains(statement, "PAR_MANAGE")])
    error_message = "State role must not gain bucket changes, PARs or permanent version deletion."
  }
  assert {
    condition     = alltrue([for statement in oci_identity_policy.state[0].statements : !strcontains(statement, " to manage objects ") || strcontains(statement, "target.object.name = '${var.state_key}'") || strcontains(statement, "target.object.name = '${var.state_key}.lock'")])
    error_message = "State content access must name only the state and lock key, without a prefix wildcard."
  }
  assert {
    condition     = contains(oci_identity_policy.state[0].statements, "Allow group id ${var.developer_group_ocid} to inspect objects in compartment id ${var.state_compartment_ocid} where target.bucket.name = '${var.state_bucket_name}'")
    error_message = "Backend workspace enumeration needs bucket-scoped metadata listing, explicitly disclosed."
  }
}

run "image_publisher_exact_repository_and_inherent_update_authority" {
  command = plan
  variables { role = "image-publisher" }
  assert {
    condition     = length(oci_identity_policy.state) == 0 && length(oci_identity_policy.application[0].statements) == 3
    error_message = "Image publisher must receive only three repository permissions."
  }
  assert {
    condition     = alltrue([for permission in ["REPOSITORY_INSPECT", "REPOSITORY_READ", "REPOSITORY_UPDATE"] : contains(oci_identity_policy.application[0].statements, "Allow group id ${var.developer_group_ocid} to manage repos in compartment id ${var.compartment_ocid} where all {target.repo.name = '${var.registry_name}', request.permission = '${permission}'}")])
    error_message = "Image publishing must not gain repository management or creation."
  }
  assert {
    condition     = output.access_review.image_update_authority == "includes-image-deletion-tags-and-signatures-not-upload-only"
    error_message = "Do not claim push-only IAM; OCI reuses UPDATE for image mutations."
  }
}

run "reject_state_role_without_key" {
  command = plan
  variables { role = "state-operator" }
  expect_failures = [oci_identity_policy.state]
}

run "reject_state_key_wildcard" {
  command = plan
  variables {
    role      = "state-operator"
    state_key = "*/app.tfstate"
  }
  expect_failures = [var.state_key]
}

run "reject_state_key_traversal" {
  command = plan
  variables {
    role      = "state-operator"
    state_key = "../app.tfstate"
  }
  expect_failures = [var.state_key]
}

run "reject_app_role_without_certificate" {
  command = plan
  variables { role = "app-deployer" }
  expect_failures = [oci_identity_policy.application]
}

run "reject_bad_certificate" {
  command = plan
  variables {
    role             = "app-deployer"
    certificate_ocid = "ocid1.vaultsecret.oc1.phx.syntheticsecret"
  }
  expect_failures = [var.certificate_ocid]
}

run "foundation_handoff_is_bound_and_not_authorization" {
  command = plan
  variables {
    environment    = "rehearsal"
    request_sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  assert {
    condition     = output.foundation.schema == "oci-kit-foundation-output/1" && output.foundation.component == "access" && output.foundation.environment == "rehearsal" && output.foundation.request_sha256 == var.request_sha256 && length(output.foundation.target) == 0 && length(output.foundation.private) == 0
    error_message = "Handoff must bind the request and transfer no resource grants or approvals."
  }
}
