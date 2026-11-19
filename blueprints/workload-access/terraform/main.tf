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
  # Explicit permission lists exclude resource moves and container-log retrieval.
  # All affected resources must belong to the dedicated application compartment.
  deployment_permissions = {
    compute-container-instances = ["COMPUTE_CONTAINER_INSTANCE_INSPECT", "COMPUTE_CONTAINER_INSTANCE_READ", "COMPUTE_CONTAINER_INSTANCE_CREATE", "COMPUTE_CONTAINER_INSTANCE_UPDATE", "COMPUTE_CONTAINER_INSTANCE_DELETE", "COMPUTE_CONTAINER_INSTANCE_START", "COMPUTE_CONTAINER_INSTANCE_STOP", "COMPUTE_CONTAINER_INSTANCE_RESTART"]
    compute-containers          = ["COMPUTE_CONTAINER_INSPECT", "COMPUTE_CONTAINER_READ", "COMPUTE_CONTAINER_CREATE", "COMPUTE_CONTAINER_UPDATE", "COMPUTE_CONTAINER_DELETE"]
    load-balancers              = ["LOAD_BALANCER_INSPECT", "LOAD_BALANCER_READ", "LOAD_BALANCER_CREATE", "LOAD_BALANCER_UPDATE", "LOAD_BALANCER_DELETE"]
    network-security-groups     = ["NETWORK_SECURITY_GROUP_INSPECT", "NETWORK_SECURITY_GROUP_READ", "NETWORK_SECURITY_GROUP_LIST_SECURITY_RULES", "NETWORK_SECURITY_GROUP_LIST_MEMBERS", "NETWORK_SECURITY_GROUP_UPDATE_MEMBERS", "NETWORK_SECURITY_GROUP_CREATE", "NETWORK_SECURITY_GROUP_UPDATE", "NETWORK_SECURITY_GROUP_DELETE", "NETWORK_SECURITY_GROUP_UPDATE_SECURITY_RULES"]
    vcns                        = ["VCN_READ", "VCN_ATTACH", "VCN_DETACH"]
  }
  deployment_app = concat(
    [for kind, permissions in local.deployment_permissions : "${local.subject} to manage ${kind} in compartment id ${var.compartment_ocid} where any {${join(", ", [for permission in permissions : "request.permission = '${permission}'"])}}"],
    [for kind in ["vnics", "subnets", "dhcp-options"] : "${local.subject} to use ${kind} in compartment id ${var.compartment_ocid}"],
    ["${local.subject} to read repos in compartment id ${var.compartment_ocid} where target.repo.name = '${var.registry_name}'"],
    var.certificate_ocid == null ? [] : [
      "${local.subject} to read leaf-certificates in compartment id ${var.compartment_ocid} where target.leaf-certificate.id = '${var.certificate_ocid}'",
      "${local.subject} to read leaf-certificate-versions in compartment id ${var.compartment_ocid} where target.leaf-certificate.id = '${var.certificate_ocid}'",
      "${local.subject} to read leaf-certificate-bundles in compartment id ${var.compartment_ocid} where all {target.leaf-certificate.id = '${var.certificate_ocid}', target.leaf-certificate.bundle-type = 'CERTIFICATE_CONTENT_PUBLIC_ONLY'}",
      "${local.subject} to manage certificate-associations in compartment id ${var.compartment_ocid} where target.leaf-certificate.id = '${var.certificate_ocid}'"
    ]
  )
  # OCI uses REPOSITORY_UPDATE for pushes AND image/tag/signature mutations.
  # It is not upload-only. REPOSITORY_MANAGE (visibility/settings) is excluded.
  publisher_app = [for permission in ["REPOSITORY_INSPECT", "REPOSITORY_READ", "REPOSITORY_UPDATE"] : "${local.subject} to manage repos in compartment id ${var.compartment_ocid} where all {target.repo.name = '${var.registry_name}', request.permission = '${permission}'}"]
  state_objects = concat(
    ["${local.subject} to read buckets in compartment id ${var.state_compartment_ocid} where target.bucket.name = '${var.state_bucket_name}'",
    "${local.subject} to inspect objects in compartment id ${var.state_compartment_ocid} where target.bucket.name = '${var.state_bucket_name}'"],
    var.state_key == null ? [] : flatten([
      for key in [var.state_key, "${var.state_key}.lock"] : [
        for permission in ["OBJECT_READ", "OBJECT_CREATE", "OBJECT_OVERWRITE", "OBJECT_DELETE"] : "${local.subject} to manage objects in compartment id ${var.state_compartment_ocid} where all {target.bucket.name = '${var.state_bucket_name}', target.object.name = '${key}', request.permission = '${permission}'}"
      ]
    ])
  )
  application_roles = {
    foundation-provisioner = local.foundation_app
    observer               = local.observer_app
    app-deployer           = local.deployment_app
    image-publisher        = local.publisher_app
  }
  state_roles = {
    foundation-provisioner = local.foundation_state
    observer               = local.observer_state
    state-operator         = local.state_objects
  }

}

resource "oci_identity_policy" "application" {
  count          = contains(keys(local.application_roles), var.role) ? 1 : 0
  compartment_id = var.compartment_ocid
  name           = "${var.name}-${var.role}"
  description    = "Reviewed human operator access for a dedicated application boundary."
  statements     = local.application_roles[var.role]
  lifecycle {
    precondition {
      condition     = var.role != "app-deployer" || var.certificate_ocid != null
      error_message = "App deployment requires the exact existing certificate in the application compartment."
    }
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
  count          = contains(keys(local.state_roles), var.role) ? 1 : 0
  compartment_id = var.state_compartment_ocid
  name           = "${var.name}-${var.role}"
  description    = "Reviewed role access to the selected state bucket and, when explicit, state objects."
  statements     = local.state_roles[var.role]
  lifecycle {
    precondition {
      condition     = var.role != "state-operator" || var.state_key != null
      error_message = "State operations require one explicit state key; named Terraform workspaces are not granted."
    }
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

# Preserve existing v0.8 policy identities when conditional role attachments are introduced.
moved {
  from = oci_identity_policy.application
  to   = oci_identity_policy.application[0]
}
moved {
  from = oci_identity_policy.state
  to   = oci_identity_policy.state[0]
}

output "access_review" {
  description = "Private review evidence. Terraform validation does not establish effective OCI permissions."
  value = {
    role                   = var.role
    application_policy_id  = try(oci_identity_policy.application[0].id, null)
    state_policy_id        = try(oci_identity_policy.state[0].id, null)
    application_actions    = try(oci_identity_policy.application[0].statements, [])
    state_actions          = try(oci_identity_policy.state[0].statements, [])
    inherited_access       = "unknown-until-administrator-review-and-negative-tests"
    deployment_permission  = var.role == "app-deployer" ? "proposed-generic-web-resources-runtime-iam-prerequisite" : "not-granted-by-this-template"
    state_object_access    = var.role == "state-operator" ? "proposed-exact-state-and-lock-objects-bucket-wide-metadata" : "not-granted-by-this-template"
    image_update_authority = var.role == "image-publisher" ? "includes-image-deletion-tags-and-signatures-not-upload-only" : "not-granted-by-this-template"
  }
}

output "foundation" {
  description = "Request-bound local handoff metadata; never an assertion of effective access."
  value = var.environment == "" ? null : {
    schema         = "oci-kit-foundation-output/1"
    component      = "access"
    environment    = var.environment
    request_sha256 = var.request_sha256
    region         = var.region
    target         = {}
    private        = {}
  }
  precondition {
    condition     = (var.environment == "") == (var.request_sha256 == "")
    error_message = "Foundation handoff requires both the named environment and request hash."
  }
}
