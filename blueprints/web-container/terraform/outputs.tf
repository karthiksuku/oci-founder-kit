output "app_url" {
  description = "Declared HTTPS origin. DNS, certificate match and working application must still be verified."
  value       = var.public_origin
}

output "load_balancer_ip" {
  value = oci_load_balancer_load_balancer.web.ip_address_details[0].ip_address
}

output "container_instance_id" {
  value = oci_container_instances_container_instance.app.id
}

output "deployed_image" {
  description = "Configured immutable image. Confirm the live OCI instance matches before acceptance."
  value       = var.app_image
}

output "environment_target" {
  value = {
    compartment_ocid = var.compartment_ocid
    region           = var.region
    name             = var.name
  }
}
