locals {
  image_path       = split("/", split("@", var.app_image)[0])
  image_repository = try(join("/", slice(local.image_path, 2, length(local.image_path))), "")
  app_environment = merge(var.public_environment, var.application_contract.background_control_environment,
    { for key, ref in var.secret_references : key => ref.secret_ocid }, {
      HOST          = "0.0.0.0"
      PORT          = tostring(var.app_port)
      PUBLIC_ORIGIN = var.public_origin
      OCI_REGION    = var.region
  })
}

resource "oci_container_instances_container_instance" "app" {
  compartment_id           = var.compartment_ocid
  availability_domain      = var.availability_domain
  display_name             = "${var.name}-app"
  shape                    = "CI.Standard.E4.Flex"
  container_restart_policy = "ALWAYS"

  shape_config {
    ocpus         = var.app_ocpus
    memory_in_gbs = var.app_memory_gbs
  }

  vnics {
    subnet_id             = var.network.private_subnet_ocid
    nsg_ids               = [oci_core_network_security_group.app.id]
    private_ip            = var.network.app_private_ip
    is_public_ip_assigned = false
  }

  containers {
    display_name          = var.name
    image_url             = var.app_image
    environment_variables = local.app_environment
    health_checks {
      health_check_type        = "HTTP"
      port                     = var.app_port
      path                     = var.health_path
      interval_in_seconds      = 15
      timeout_in_seconds       = 5
      failure_threshold        = 3
      initial_delay_in_seconds = 30
    }
  }

  lifecycle {
    precondition {
      condition = (data.oci_core_subnet.private.vcn_id == var.network.vcn_ocid &&
        data.oci_core_subnet.private.prohibit_public_ip_on_vnic &&
      try(cidrhost("${var.network.app_private_ip}/${split("/", data.oci_core_subnet.private.cidr_block)[1]}", 0) == cidrhost(data.oci_core_subnet.private.cidr_block, 0), false))
      error_message = "The app must use a private subnet in the selected VCN and an address within that subnet."
    }
    precondition {
      condition     = var.app_memory_gbs >= var.app_ocpus && var.app_memory_gbs <= var.app_ocpus * 64
      error_message = "CI.Standard.E4.Flex requires 1 to 64 GB per OCPU. Verify current regional shape limits separately."
    }
    precondition {
      condition     = local.image_repository == var.registry.repository_name
      error_message = "The immutable image must belong to the selected repository."
    }
    precondition {
      condition = (can(regex("^[0-9a-f]{64}$", var.application_contract.evidence_sha256)) &&
        contains(["absent", "disabled"], var.application_contract.background_work) &&
      (var.application_contract.background_work != "disabled" || length(var.application_contract.background_control_environment) > 0))
      error_message = "Review evidence for this image: background jobs must be absent or verified disabled by real application controls. Target worker takeover is a separate operation."
    }
    precondition {
      condition     = length(var.secret_references) == 0 || var.application_contract.vault_references_implemented
      error_message = "The image must implement and test resource-principal Vault retrieval before secret references can be injected."
    }
    precondition {
      condition     = length(setintersection(toset(keys(var.public_environment)), toset(keys(var.application_contract.background_control_environment)))) == 0
      error_message = "Background controls must not override public settings; define each setting once."
    }
  }

  depends_on = [oci_identity_policy.registry, oci_identity_policy.secrets]
}
