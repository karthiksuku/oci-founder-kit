output "container_instance_id" { value = oci_container_instances_container_instance.worker.id }
output "queue_id" { value = oci_queue_queue.jobs.id }
output "queue_endpoint" { value = oci_queue_queue.jobs.messages_endpoint }
output "deployed_image" { value = var.app_image }
output "component_role" { value = "worker" }
