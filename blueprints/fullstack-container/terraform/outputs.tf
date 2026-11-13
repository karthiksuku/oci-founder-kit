output "app_url" {
  description = "Open this in a browser from an allowed client range."
  value = local.api_gateway_enabled ? local.public_origin : (
    var.production == null ? "http://${oci_load_balancer_load_balancer.web[0].ip_address_details[0].ip_address}" : local.public_origin
  )
}

output "load_balancer_ip" {
  description = "DNS target; changing DNS requires separate cutover approval."
  value       = local.load_balancer_enabled ? oci_load_balancer_load_balancer.web[0].ip_address_details[0].ip_address : null
}

output "api_gateway_hostname" {
  description = "OCI-managed HTTPS hostname; use the actual value for the OIDC callback after the approved gateway bootstrap."
  value       = local.api_gateway_enabled ? oci_apigateway_gateway.web[0].hostname : null
}

output "api_gateway_id" {
  value = local.api_gateway_enabled ? oci_apigateway_gateway.web[0].id : null
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
