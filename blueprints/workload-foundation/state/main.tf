variable "namespace" { type = string }
variable "state_key" { type = string }
variable "workspace_key_prefix" { type = string }
resource "oci_objectstorage_bucket" "state" {
  compartment_id = var.compartment_ocid
  namespace      = var.namespace
  name           = "${var.name}-${var.environment}-tfstate"
  access_type    = "NoPublicAccess"
  versioning     = "Enabled"
  storage_tier   = "Standard"
  lifecycle { prevent_destroy = true }
}
output "foundation" {
  value = {
    schema         = "oci-kit-foundation-output/1"
    component      = "state"
    environment    = var.environment
    request_sha256 = var.request_sha256
    region         = var.region
    target         = {}
    private        = {}
    backend = {
      region               = var.region
      namespace            = var.namespace
      bucket               = oci_objectstorage_bucket.state.name
      key                  = var.state_key
      workspace_key_prefix = var.workspace_key_prefix
    }
  }
}
