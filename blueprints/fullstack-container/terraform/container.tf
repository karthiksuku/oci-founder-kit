data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

locals {
  db_endpoint = data.oci_psql_db_system_connection_detail.main.primary_db_endpoint[0]
  # URL-encode credentials: the generated password contains special characters.
  database_url = local.production_enabled ? null : format("postgres://%s:%s@%s:%d/postgres", "taskboard", urlencode(random_password.db[0].result),
  local.db_endpoint.fqdn, local.db_endpoint.port)
  app_environment = merge({
    HOST             = local.app_private_ip
    PORT             = tostring(local.app_port)
    APP_MODE         = local.production_enabled ? "production" : "sandbox"
    DATABASE_CA_CERT = data.oci_psql_db_system_connection_detail.main.ca_certificate
    OCI_BUCKET       = oci_objectstorage_bucket.uploads.name
    OCI_NAMESPACE    = data.oci_objectstorage_namespace.ns.namespace
    OCI_REGION       = var.region
    OCI_AUTH         = "resource-principal"
    }, var.production == null ? {
    DATABASE_URL = local.database_url
    } : {
    PUBLIC_ORIGIN                    = local.public_origin
    OIDC_ISSUER                      = var.production.oidc_issuer
    OIDC_DISCOVERY_URL               = var.production.oidc_discovery_url == null ? "" : var.production.oidc_discovery_url
    OIDC_CLIENT_ID                   = var.production.oidc_client_id
    OIDC_CLIENT_SECRET_OCID          = var.production.oidc_client_secret_ocid
    SESSION_SECRET_OCID              = var.production.session_secret_ocid
    DATABASE_PASSWORD_SECRET_OCID    = var.production.database_secret_ocid
    DATABASE_PASSWORD_SECRET_VERSION = tostring(var.production.database_secret_version)
    DATABASE_HOST                    = local.db_endpoint.fqdn
    DATABASE_PORT                    = tostring(local.db_endpoint.port)
    DATABASE_NAME                    = "postgres"
    DATABASE_USER                    = "taskboard"
    TRUST_PROXY_CIDRS                = local.api_gateway_enabled ? local.gateway_cidr : local.public_cidr
  })
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

    # Production injects only secret identifiers; the server retrieves values.
    environment_variables = local.app_environment

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

  lifecycle {
    precondition {
      condition     = !local.api_gateway_enabled || local.production_enabled
      error_message = "API Gateway may be bootstrapped separately, but its app requires complete production OIDC/Vault configuration."
    }
    precondition {
      condition     = !local.production_enabled || can(regex("@sha256:[0-9a-f]{64}$", var.app_image))
      error_message = "Production app_image must use an immutable sha256 image digest."
    }
  }

  depends_on = [oci_identity_policy.app, oci_identity_policy.runtime_secrets]
}
