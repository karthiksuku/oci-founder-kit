# Lets the app container reach its bucket as a resource principal, with no
# stored keys. Scoped to container instances in this compartment and to this
# bucket: objects, plus PAR_MANAGE for short-lived upload and download links.
resource "oci_identity_dynamic_group" "app" {
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = "${var.name}-containers"
  description    = "Container instances of ${var.name} in its compartment"
  matching_rule  = "ALL {resource.type = 'computecontainerinstance', resource.compartment.id = '${var.compartment_ocid}'}"
}

resource "oci_identity_policy" "app" {
  provider       = oci.home
  compartment_id = var.compartment_ocid
  name           = "${var.name}-app"
  description    = "Object Storage access for ${var.name} containers, limited to its bucket"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.app.name} to manage objects in compartment id ${var.compartment_ocid} where target.bucket.name = '${oci_objectstorage_bucket.uploads.name}'",
    "Allow dynamic-group ${oci_identity_dynamic_group.app.name} to manage buckets in compartment id ${var.compartment_ocid} where all {target.bucket.name = '${oci_objectstorage_bucket.uploads.name}', request.permission = 'PAR_MANAGE'}",
  ]
}
