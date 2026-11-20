# Administrative prerequisite: review VSS service access separately. No IAM is created here.
variable "compartment_id" {
  type = string
  validation {
    condition     = can(regex("^ocid1\\.compartment\\.", var.compartment_id))
    error_message = "Choose the dedicated registry compartment."
  }
}
variable "repository_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9]+([._/-][a-z0-9]+)*$", var.repository_name))
    error_message = "Choose one existing repository display name. Wildcards are not allowed."
  }
}
resource "oci_vulnerability_scanning_container_scan_recipe" "workload" {
  compartment_id = var.compartment_id
  display_name   = "founder-workload-image-scan"
  image_count    = 1
  scan_settings {
    scan_level = "STANDARD"
  }
}
resource "oci_vulnerability_scanning_container_scan_target" "workload" {
  compartment_id           = var.compartment_id
  container_scan_recipe_id = oci_vulnerability_scanning_container_scan_recipe.workload.id
  display_name             = "founder-workload-image-target"
  target_registry {
    type           = "OCIR"
    compartment_id = var.compartment_id
    repositories   = [var.repository_name]
  }
}
