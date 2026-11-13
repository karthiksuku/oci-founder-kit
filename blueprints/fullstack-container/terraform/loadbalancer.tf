resource "oci_load_balancer_load_balancer" "web" {
  count                      = local.load_balancer_enabled ? 1 : 0
  compartment_id             = var.compartment_ocid
  display_name               = "${var.name}-lb"
  shape                      = "flexible"
  subnet_ids                 = [oci_core_subnet.public[0].id]
  is_private                 = false
  network_security_group_ids = [oci_core_network_security_group.lb[0].id]

  shape_details {
    minimum_bandwidth_in_mbps = 10
    maximum_bandwidth_in_mbps = 10
  }

  lifecycle {
    precondition {
      condition = var.production == null ? true : (
        var.production.public_origin != null && var.production.certificate_ocid != null
      )
      error_message = "Production load-balancer ingress requires both public_origin and certificate_ocid."
    }
  }
}

resource "oci_load_balancer_backend_set" "app" {
  count            = local.load_balancer_enabled ? 1 : 0
  load_balancer_id = oci_load_balancer_load_balancer.web[0].id
  name             = "app"
  policy           = "ROUND_ROBIN"

  health_checker {
    protocol    = "HTTP"
    port        = local.app_port
    url_path    = "/readyz"
    return_code = 200
  }
}

resource "oci_load_balancer_backend" "app" {
  count            = local.load_balancer_enabled ? 1 : 0
  load_balancer_id = oci_load_balancer_load_balancer.web[0].id
  backendset_name  = oci_load_balancer_backend_set.app[0].name
  ip_address       = local.app_private_ip
  port             = local.app_port
}

# HTTP exists only in restricted sandbox mode. Production has no HTTP listener.
resource "oci_load_balancer_listener" "http" {
  count                    = local.load_balancer_enabled && !local.production_enabled ? 1 : 0
  load_balancer_id         = oci_load_balancer_load_balancer.web[0].id
  name                     = "http"
  default_backend_set_name = oci_load_balancer_backend_set.app[0].name
  port                     = 80
  protocol                 = "HTTP"
}

resource "oci_load_balancer_listener" "https" {
  count                    = local.load_balancer_enabled && local.production_enabled ? 1 : 0
  load_balancer_id         = oci_load_balancer_load_balancer.web[0].id
  name                     = "https"
  default_backend_set_name = oci_load_balancer_backend_set.app[0].name
  port                     = 443
  protocol                 = "HTTP"
  ssl_configuration {
    certificate_ids   = compact([var.production.certificate_ocid])
    protocols         = ["TLSv1.2", "TLSv1.3"]
    cipher_suite_name = "oci-tls-12-13-ssl-cipher-suite-v3"
  }
}
