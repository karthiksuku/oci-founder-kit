# Optional and visible in the saved plan. Default false reuses administrator-
# reviewed IAM. This membership covers ALL container instances in this dedicated
# environment compartment; do not use a shared compartment.
resource "oci_identity_dynamic_group" "runtime" {
  count          = var.manage_runtime_iam ? 1 : 0
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = "${var.name}-containers"
  description    = "Container Instances in the dedicated ${var.name} environment compartment"
  matching_rule  = "ALL {resource.type = 'computecontainerinstance', resource.compartment.id = '${var.compartment_ocid}'}"
}

resource "oci_identity_policy" "registry" {
  count          = var.manage_runtime_iam ? 1 : 0
  provider       = oci.home
  compartment_id = var.registry.compartment_ocid
  name           = "${var.name}-image-pull"
  description    = "Read the selected private image repository only"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.runtime[0].name} to read repos in compartment id ${var.registry.compartment_ocid} where target.repo.name = '${var.registry.repository_name}'"
  ]
}

resource "oci_identity_policy" "secrets" {
  for_each       = var.manage_runtime_iam ? var.secret_references : {}
  provider       = oci.home
  compartment_id = each.value.compartment_ocid
  name           = "${var.name}-${lower(replace(each.key, "_", "-"))}"
  description    = "Read only the selected runtime secret bundle; secret contents never enter Terraform"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.runtime[0].name} to read secret-bundles in compartment id ${each.value.compartment_ocid} where target.secret.id = '${each.value.secret_ocid}'"
  ]
}
