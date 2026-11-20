mock_provider "oci" {}
variables {
  region              = "us-phoenix-1"
  config_file_profile = "test"
  tenancy_ocid        = "ocid1.tenancy.oc1..synthetic"
  auth                = "SecurityToken"
  compartment_id      = "ocid1.compartment.oc1..synthetic"
  repository_name     = "founder/rehearsal"
}
run "selected_repository_only" {
  command = plan
  assert {
    condition     = oci_vulnerability_scanning_container_scan_recipe.workload.image_count == 1 && oci_vulnerability_scanning_container_scan_recipe.workload.scan_settings[0].scan_level == "STANDARD"
    error_message = "Retain a bounded initial registry scan."
  }
  assert {
    condition     = length(oci_vulnerability_scanning_container_scan_target.workload.target_registry[0].repositories) == 1 && contains(oci_vulnerability_scanning_container_scan_target.workload.target_registry[0].repositories, var.repository_name) && oci_vulnerability_scanning_container_scan_target.workload.target_registry[0].compartment_id == var.compartment_id
    error_message = "The target must refer only to the requested compartment and repository."
  }
}
run "no_wildcard_repository" {
  command = plan
  variables {
    repository_name = "*"
  }
  expect_failures = [var.repository_name]
}
