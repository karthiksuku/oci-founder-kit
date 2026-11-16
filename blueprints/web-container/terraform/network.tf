data "oci_core_subnet" "public" {
  subnet_id = var.network.public_subnet_ocid
}

data "oci_core_subnet" "private" {
  subnet_id = var.network.private_subnet_ocid
}

resource "oci_core_network_security_group" "lb" {
  compartment_id = var.compartment_ocid
  vcn_id         = var.network.vcn_ocid
  display_name   = "${var.name}-lb"
}

resource "oci_core_network_security_group" "app" {
  compartment_id = var.compartment_ocid
  vcn_id         = var.network.vcn_ocid
  display_name   = "${var.name}-app"
}

resource "oci_core_network_security_group_security_rule" "lb_in_https" {
  for_each                  = var.allowed_ingress_cidrs
  network_security_group_id = oci_core_network_security_group.lb.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_network_security_group_security_rule" "lb_out_app" {
  network_security_group_id = oci_core_network_security_group.lb.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = oci_core_network_security_group.app.id
  destination_type          = "NETWORK_SECURITY_GROUP"
  tcp_options {
    destination_port_range {
      min = var.app_port
      max = var.app_port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_in_lb" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = oci_core_network_security_group.lb.id
  source_type               = "NETWORK_SECURITY_GROUP"
  tcp_options {
    destination_port_range {
      min = var.app_port
      max = var.app_port
    }
  }
}

# OCI NSGs do not filter by hostname. TLS destination and certificate validation
# remain application obligations, including retained cross-cloud dependencies.
resource "oci_core_network_security_group_security_rule" "app_out_https" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_out_dependencies" {
  for_each                  = var.dependency_egress
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = each.value.destination_cidr
  destination_type          = "CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = each.value.port
      max = each.value.port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "dns_udp" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "17"
  destination               = "169.254.169.254/32"
  destination_type          = "CIDR_BLOCK"
  udp_options {
    destination_port_range {
      min = 53
      max = 53
    }
  }
}

resource "oci_core_network_security_group_security_rule" "dns_tcp" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = "169.254.169.254/32"
  destination_type          = "CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = 53
      max = 53
    }
  }
}
