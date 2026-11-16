locals {
  # Dynamic-group names are tenancy-wide, even when membership is compartment-scoped.
  worker_identity_name = "${var.name}-worker-${substr(sha256(var.compartment_ocid), 0, 10)}"
}

# Optional and visible in the saved plan. Default false reuses administrator-
# reviewed IAM. This membership covers ALL container instances in this dedicated
# environment compartment; do not use a shared compartment.
resource "oci_identity_dynamic_group" "runtime" {
  count          = var.manage_runtime_iam ? 1 : 0
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = "${local.worker_identity_name}-containers"
  description    = "Container Instances in the dedicated ${var.name} environment compartment"
  matching_rule  = "ALL {resource.type = 'computecontainerinstance', resource.compartment.id = '${var.compartment_ocid}'}"
}

resource "oci_identity_policy" "registry" {
  count          = var.manage_runtime_iam ? 1 : 0
  provider       = oci.home
  compartment_id = var.registry.compartment_ocid
  name           = "${local.worker_identity_name}-image-pull"
  description    = "Read the selected private image repository only"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.runtime[0].name} to read repos in compartment id ${var.registry.compartment_ocid} where target.repo.name = '${var.registry.repository_name}'"
  ]
}

resource "oci_identity_policy" "secrets" {
  for_each       = var.manage_runtime_iam ? var.secret_references : {}
  provider       = oci.home
  compartment_id = each.value.compartment_ocid
  name           = "${local.worker_identity_name}-${lower(replace(each.key, "_", "-"))}"
  description    = "Read only the selected runtime secret bundle; secret contents never enter Terraform"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.runtime[0].name} to read secret-bundles in compartment id ${each.value.compartment_ocid} where target.secret.id = '${each.value.secret_ocid}'"
  ]
}

# Only the worker publishes the durable outbox and consumes jobs. The web runtime
# has no Queue policy, and must live outside this dynamic group's compartment.
resource "oci_identity_policy" "queue" {
  count          = var.manage_runtime_iam ? 1 : 0
  provider       = oci.home
  compartment_id = var.compartment_ocid
  name           = "${local.worker_identity_name}-queue"
  description    = "Produce and consume the selected queue; no queue administration"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.runtime[0].name} to use queue-push in compartment id ${var.compartment_ocid} where target.queue.id = '${oci_queue_queue.jobs.id}'",
    "Allow dynamic-group ${oci_identity_dynamic_group.runtime[0].name} to use queue-pull in compartment id ${var.compartment_ocid} where target.queue.id = '${oci_queue_queue.jobs.id}'"
  ]
}
