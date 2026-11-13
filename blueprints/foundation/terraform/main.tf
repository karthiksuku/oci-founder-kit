resource "oci_identity_compartment" "workload" {
  compartment_id = var.compartment_ocid
  name           = var.workload_name
  description    = "Workload boundary managed by OCI Founder Kit; access reviewed by the owner."
  enable_delete  = true
  freeform_tags = {
    managed_by = "oci-founder-kit"
    workload   = var.workload_name
  }
}

# Inventory only. Workload deployment permissions are separate reviewed policies.
resource "oci_identity_policy" "developer_inspect" {
  compartment_id = oci_identity_compartment.workload.id
  name           = "${var.workload_name}-developer-inspect"
  description    = "Allow the selected developer group to inspect this workload boundary."
  statements = [
    "Allow group id ${var.developer_group_ocid} to inspect all-resources in compartment id ${oci_identity_compartment.workload.id}"
  ]
}
