# OCI owns the hostname and frontend certificate. Bootstrap only this gateway
# through an explicitly reviewed targeted plan; configure OIDC before the full plan.
resource "oci_apigateway_gateway" "web" {
  count                      = local.api_gateway_enabled ? 1 : 0
  compartment_id             = var.compartment_ocid
  display_name               = "${var.name}-gateway"
  endpoint_type              = "PUBLIC"
  subnet_id                  = oci_core_subnet.gateway[0].id
  network_security_group_ids = [oci_core_network_security_group.gateway[0].id]

  # Include the restrictive rules even when the owner approves a gateway-only
  # bootstrap target. The gateway has no app route until the deployment below.
  depends_on = [
    oci_core_network_security_group_security_rule.gateway_in_https,
    oci_core_network_security_group_security_rule.gateway_out_app,
    oci_core_network_security_group_security_rule.app_in_gateway,
  ]

  lifecycle {
    precondition {
      condition     = alltrue([for cidr in var.allowed_ingress_cidrs : can(cidrnetmask(cidr)) && endswith(cidr, "/32")])
      error_message = "API Gateway rehearsal ingress requires explicit tester IPv4 /32 addresses."
    }
    precondition {
      condition     = tonumber(split("/", local.gateway_cidr)[1]) <= 26
      error_message = "The dedicated gateway subnet must be /26 or larger to leave at least 32 addresses free."
    }
    precondition {
      condition     = can(regex("^ocid1\\.tenancy\\.oc1\\.\\.", var.tenancy_ocid))
      error_message = "This managed-hostname gateway reference is supported in the commercial OC1 realm."
    }
    precondition {
      condition = var.production == null ? true : (
        var.production.public_origin == null && var.production.certificate_ocid == null
      )
      error_message = "API Gateway derives its HTTPS origin and certificate; omit public_origin and certificate_ocid."
    }
  }
}

resource "oci_apigateway_deployment" "app" {
  count          = local.api_gateway_enabled ? 1 : 0
  compartment_id = var.compartment_ocid
  gateway_id     = oci_apigateway_gateway.web[0].id
  display_name   = "${var.name}-app"
  path_prefix    = "/"

  specification {
    # Login callbacks and session-related URLs must not appear in gateway logs.
    logging_policies {
      access_log {
        is_enabled = false
      }
      execution_log {
        is_enabled = false
      }
    }
    routes {
      path    = "/{path*}"
      methods = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
      backend {
        type                       = "HTTP_BACKEND"
        url                        = "http://${local.app_private_ip}:${local.app_port}/$${request.path[path]}"
        connect_timeout_in_seconds = 10
        read_timeout_in_seconds    = 30
        send_timeout_in_seconds    = 30
      }
      request_policies {
        header_transformations {
          set_headers {
            items {
              name      = "X-Forwarded-Proto"
              values    = ["https"]
              if_exists = "OVERWRITE"
            }
          }
        }
      }
      # No cache or query transformation policy: the app owns authentication,
      # cookies, callback queries, CSRF and authenticated binary transfers.
    }
  }

  lifecycle {
    precondition {
      condition     = local.production_enabled
      error_message = "The gateway app route requires complete production OIDC/Vault configuration."
    }
  }
  depends_on = [oci_container_instances_container_instance.app]
}
