output "app_url" {
  description = "Open this in a browser from an allowed client range."
  value       = var.production == null ? "http://${oci_load_balancer_load_balancer.web.ip_address_details[0].ip_address}" : var.production.public_origin
}

output "load_balancer_ip" {
  description = "DNS target; changing DNS requires separate cutover approval."
  value       = oci_load_balancer_load_balancer.web.ip_address_details[0].ip_address
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
