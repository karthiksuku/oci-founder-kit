data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

locals {
  db_endpoint = data.oci_psql_db_system_connection_detail.main.primary_db_endpoint[0]
  # URL-encode credentials: the generated password contains special characters.
  database_url = format("postgres://%s:%s@%s:%d/postgres", "taskboard", urlencode(random_password.db.result),
  local.db_endpoint.fqdn, local.db_endpoint.port)
}

resource "oci_container_instances_container_instance" "app" {
  compartment_id           = var.compartment_ocid
  availability_domain      = local.ads[0].name
  display_name             = "${var.name}-app"
  shape                    = "CI.Standard.E4.Flex"
  container_restart_policy = "ALWAYS"

  shape_config {
    ocpus         = var.app_ocpus
    memory_in_gbs = var.app_memory_gbs
  }

  vnics {
    subnet_id             = oci_core_subnet.private.id
    nsg_ids               = [oci_core_network_security_group.app.id]
    private_ip            = local.app_private_ip
    is_public_ip_assigned = false
  }

  containers {
    display_name = "taskboard"
    image_url    = var.app_image

    # Sandbox default: environment variables are visible to anyone who can read
    # this container instance. For production, read the database password from
    # OCI Vault at startup with the resource principal.
    environment_variables = {
      HOST             = local.app_private_ip
      PORT             = tostring(local.app_port)
      DATABASE_URL     = local.database_url
      DATABASE_CA_CERT = data.oci_psql_db_system_connection_detail.main.ca_certificate
      OCI_BUCKET       = oci_objectstorage_bucket.uploads.name
      OCI_NAMESPACE    = data.oci_objectstorage_namespace.ns.namespace
      OCI_REGION       = var.region
    }

    health_checks {
      health_check_type        = "HTTP"
      port                     = local.app_port
      path                     = "/healthz"
      interval_in_seconds      = 15
      timeout_in_seconds       = 5
      failure_threshold        = 3
      initial_delay_in_seconds = 20
    }
  }

  depends_on = [oci_identity_policy.app]
}
