resource "oci_artifacts_container_repository" "app" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.name}-${var.environment}"
  is_public      = false
  # Digest-only image publication assigns no mutable tag.
  is_immutable = false
  lifecycle { prevent_destroy = true }
}
output "foundation" {
  value = {
    schema         = "oci-kit-foundation-output/1"
    component      = "registry"
    environment    = var.environment
    request_sha256 = var.request_sha256
    region         = var.region
    target         = { compartment_id = var.compartment_ocid, registry_id = oci_artifacts_container_repository.app.id }
    private        = {}
  }
}
