output "workload_compartment_ocid" {
  description = "Use privately as the application's target compartment; do not publish real OCIDs."
  value       = oci_identity_compartment.workload.id
}

output "developer_policy_ocid" {
  description = "Inspection policy for verification and an approved cleanup."
  value       = oci_identity_policy.developer_inspect.id
}
