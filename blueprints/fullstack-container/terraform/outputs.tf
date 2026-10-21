output "app_url" {
  description = "Open this in a browser from an allowed client range."
  value       = "http://${oci_load_balancer_load_balancer.web.ip_address_details[0].ip_address}"
}

output "bucket" {
  value = oci_objectstorage_bucket.uploads.name
}

output "database_endpoint" {
  value = local.db_endpoint.fqdn
}

output "container_instance_id" {
  value = oci_container_instances_container_instance.app.id
}
