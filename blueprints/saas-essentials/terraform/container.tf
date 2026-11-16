data "oci_core_subnet" "private" { subnet_id = var.network.private_subnet_ocid }
resource "oci_core_network_security_group" "worker" {
  compartment_id = var.compartment_ocid
  vcn_id         = var.network.vcn_ocid
  display_name   = "${var.name}-worker"
}
resource "oci_core_network_security_group_security_rule" "egress" {
  for_each                  = var.egress
  network_security_group_id = oci_core_network_security_group.worker.id
  direction                 = "EGRESS"
  protocol                  = each.value.protocol
  destination               = each.value.cidr
  destination_type          = "CIDR_BLOCK"
  dynamic "tcp_options" {
    for_each = each.value.protocol == "6" ? [each.value.port] : []
    content {
      destination_port_range {
        min = tcp_options.value
        max = tcp_options.value
      }
    }
  }
  dynamic "udp_options" {
    for_each = each.value.protocol == "17" ? [each.value.port] : []
    content {
      destination_port_range {
        min = udp_options.value
        max = udp_options.value
      }
    }
  }
}
resource "oci_queue_queue" "jobs" {
  compartment_id                   = var.compartment_ocid
  display_name                     = "${var.name}-jobs"
  dead_letter_queue_delivery_count = 10
  retention_in_seconds             = 604800
  visibility_in_seconds            = 60
  timeout_in_seconds               = 20
}
resource "oci_container_instances_container_instance" "worker" {
  compartment_id           = var.compartment_ocid
  availability_domain      = var.availability_domain
  display_name             = "${var.name}-worker"
  shape                    = "CI.Standard.E4.Flex"
  container_restart_policy = "ALWAYS"
  shape_config {
    ocpus         = var.app_ocpus
    memory_in_gbs = var.app_memory_gbs
  }
  vnics {
    subnet_id             = var.network.private_subnet_ocid
    nsg_ids               = [oci_core_network_security_group.worker.id]
    private_ip            = var.network.app_private_ip
    is_public_ip_assigned = false
  }
  containers {
    display_name      = "worker"
    image_url         = var.app_image
    command           = ["node"]
    arguments         = ["saas-essentials/app/src/worker.js"]
    working_directory = "/kit/blueprints"
    environment_variables = merge(var.public_environment, { for key, ref in var.secret_references : key => ref.secret_ocid }, {
      APP_MODE           = "production"
      SAAS_ENVIRONMENT   = var.name
      OCI_QUEUE_ID       = oci_queue_queue.jobs.id
      OCI_QUEUE_ENDPOINT = oci_queue_queue.jobs.messages_endpoint
    })
  }
  lifecycle {
    precondition {
      condition     = var.compartment_ocid != var.web_compartment_ocid
      error_message = "The worker needs a separate dedicated compartment; web identity membership must not include workers."
    }
    precondition {
      condition     = data.oci_core_subnet.private.prohibit_public_ip_on_vnic && data.oci_core_subnet.private.vcn_id == var.network.vcn_ocid
      error_message = "Select a reviewed private subnet in this VCN."
    }
    precondition {
      condition     = var.app_memory_gbs >= var.app_ocpus && var.app_memory_gbs <= var.app_ocpus * 64
      error_message = "Review E4 memory/OCPU sizing."
    }
    precondition {
      condition     = join("/", slice(split("/", split("@", var.app_image)[0]), 2, length(split("/", split("@", var.app_image)[0])))) == var.registry.repository_name
      error_message = "The image must belong to the reviewed worker repository."
    }
  }
  depends_on = [oci_identity_policy.registry, oci_identity_policy.secrets, oci_identity_policy.queue]
}
