variable "compartment_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1\\.compartment\\.", var.compartment_ocid))
    error_message = "Select an authorized non-root parent compartment."
  }
}
resource "oci_identity_compartment" "app" {
  compartment_id = var.compartment_ocid
  name           = "${var.name}-${var.environment}-app"
  description    = "Dedicated application boundary. Runtime permissions require a separate reviewed policy."
  enable_delete  = false
  lifecycle { prevent_destroy = true }
}
resource "oci_identity_compartment" "state" {
  compartment_id = var.compartment_ocid
  name           = "${var.name}-${var.environment}-state"
  description    = "Dedicated private state boundary. Inherited access requires administrator review."
  enable_delete  = false
  lifecycle { prevent_destroy = true }
}
output "foundation" {
  value = {
    schema         = "oci-kit-foundation-output/1"
    component      = "compartments"
    environment    = var.environment
    request_sha256 = var.request_sha256
    region         = var.region
    target         = { compartment_id = oci_identity_compartment.app.id }
    private        = { state_compartment_id = oci_identity_compartment.state.id }
  }
}
