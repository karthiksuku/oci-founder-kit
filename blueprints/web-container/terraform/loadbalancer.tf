resource "oci_load_balancer_load_balancer" "web" {
  compartment_id             = var.compartment_ocid
  display_name               = "${var.name}-lb"
  shape                      = "flexible"
  subnet_ids                 = [var.network.public_subnet_ocid]
  is_private                 = false
  network_security_group_ids = [oci_core_network_security_group.lb.id]
  shape_details {
    minimum_bandwidth_in_mbps = 10
    maximum_bandwidth_in_mbps = 10
  }
  lifecycle {
    precondition {
      condition     = data.oci_core_subnet.public.vcn_id == var.network.vcn_ocid && !data.oci_core_subnet.public.prohibit_public_ip_on_vnic
      error_message = "The HTTPS load balancer requires a public subnet in the selected VCN."
    }
  }
}

resource "oci_load_balancer_backend_set" "app" {
  load_balancer_id = oci_load_balancer_load_balancer.web.id
  name             = "app"
  policy           = "ROUND_ROBIN"
  health_checker {
    protocol    = "HTTP"
    port        = var.app_port
    url_path    = var.health_path
    return_code = 200
  }
}

resource "oci_load_balancer_backend" "app" {
  load_balancer_id = oci_load_balancer_load_balancer.web.id
  backendset_name  = oci_load_balancer_backend_set.app.name
  ip_address       = var.network.app_private_ip
  port             = var.app_port
  depends_on       = [oci_container_instances_container_instance.app]
}

resource "oci_load_balancer_listener" "https" {
  load_balancer_id         = oci_load_balancer_load_balancer.web.id
  name                     = "https"
  default_backend_set_name = oci_load_balancer_backend_set.app.name
  port                     = 443
  protocol                 = "HTTP"
  ssl_configuration {
    certificate_ids   = [var.certificate_ocid]
    protocols         = ["TLSv1.2", "TLSv1.3"]
    cipher_suite_name = "oci-tls-12-13-ssl-cipher-suite-v3"
  }
}
