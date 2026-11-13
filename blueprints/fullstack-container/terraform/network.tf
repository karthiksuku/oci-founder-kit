locals {
  public_cidr    = cidrsubnet(var.vcn_cidr, 8, 1)
  private_cidr   = cidrsubnet(var.vcn_cidr, 8, 2)
  gateway_cidr   = cidrsubnet(var.vcn_cidr, 8, 3)
  app_private_ip = cidrhost(local.private_cidr, 10)
  app_port       = 8080
}

data "oci_core_services" "all" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

resource "oci_core_vcn" "main" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${var.name}-vcn"
  dns_label      = replace(var.name, "-", "")
}

resource "oci_core_internet_gateway" "main" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.name}-igw"
}

resource "oci_core_nat_gateway" "main" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.name}-nat"
}

resource "oci_core_service_gateway" "main" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.name}-sgw"
  services {
    service_id = data.oci_core_services.all.services[0].id
  }
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.name}-public-rt"
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.main.id
  }
}

resource "oci_core_route_table" "private" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.name}-private-rt"
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_nat_gateway.main.id
  }
  route_rules {
    destination       = data.oci_core_services.all.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.main.id
  }
}

# An empty security list replaces the VCN default (which allows SSH from anywhere).
# All traffic rules live in the network security groups below.
resource "oci_core_security_list" "none" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.name}-no-rules"
}

resource "oci_core_subnet" "public" {
  count             = local.load_balancer_enabled ? 1 : 0
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.main.id
  cidr_block        = local.public_cidr
  display_name      = "${var.name}-public"
  dns_label         = "pub"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.none.id]
}

# A dedicated regional subnet keeps the trusted gateway proxy range separate
# from the load-balancer and application subnets.
resource "oci_core_subnet" "gateway" {
  count                      = local.api_gateway_enabled ? 1 : 0
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.main.id
  cidr_block                 = local.gateway_cidr
  display_name               = "${var.name}-gateway"
  dns_label                  = "gateway"
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.none.id]
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_subnet" "private" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.main.id
  cidr_block                 = local.private_cidr
  display_name               = "${var.name}-private"
  dns_label                  = "priv"
  route_table_id             = oci_core_route_table.private.id
  security_list_ids          = [oci_core_security_list.none.id]
  prohibit_public_ip_on_vnic = true
}

resource "oci_core_network_security_group" "lb" {
  count          = local.load_balancer_enabled ? 1 : 0
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.name}-lb"
}

resource "oci_core_network_security_group" "gateway" {
  count          = local.api_gateway_enabled ? 1 : 0
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.name}-gateway"
}

resource "oci_core_network_security_group" "app" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.name}-app"
}

resource "oci_core_network_security_group" "db" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.name}-db"
}

resource "oci_core_network_security_group_security_rule" "lb_in_http" {
  for_each                  = local.load_balancer_enabled && !local.production_enabled ? toset(var.allowed_ingress_cidrs) : toset([])
  network_security_group_id = oci_core_network_security_group.lb[0].id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  description               = "HTTP from an allowed client range"
  tcp_options {
    destination_port_range {
      min = 80
      max = 80
    }
  }
}

resource "oci_core_network_security_group_security_rule" "lb_in_https" {
  for_each                  = local.load_balancer_enabled && local.production_enabled ? toset(var.allowed_ingress_cidrs) : toset([])
  network_security_group_id = oci_core_network_security_group.lb[0].id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  description               = "HTTPS from an allowed client range"
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_network_security_group_security_rule" "lb_out_app" {
  count                     = local.load_balancer_enabled ? 1 : 0
  network_security_group_id = oci_core_network_security_group.lb[0].id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = oci_core_network_security_group.app.id
  destination_type          = "NETWORK_SECURITY_GROUP"
  description               = "Load balancer to the app"
  tcp_options {
    destination_port_range {
      min = local.app_port
      max = local.app_port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_in_lb" {
  count                     = local.load_balancer_enabled ? 1 : 0
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = oci_core_network_security_group.lb[0].id
  source_type               = "NETWORK_SECURITY_GROUP"
  description               = "App traffic from the load balancer only"
  tcp_options {
    destination_port_range {
      min = local.app_port
      max = local.app_port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "gateway_in_https" {
  for_each                  = local.api_gateway_enabled ? toset(var.allowed_ingress_cidrs) : toset([])
  network_security_group_id = oci_core_network_security_group.gateway[0].id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  description               = "HTTPS from an explicitly selected tester IPv4 address"
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_network_security_group_security_rule" "gateway_out_app" {
  count                     = local.api_gateway_enabled ? 1 : 0
  network_security_group_id = oci_core_network_security_group.gateway[0].id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = oci_core_network_security_group.app.id
  destination_type          = "NETWORK_SECURITY_GROUP"
  description               = "Gateway to the private app only"
  tcp_options {
    destination_port_range {
      min = local.app_port
      max = local.app_port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_in_gateway" {
  count                     = local.api_gateway_enabled ? 1 : 0
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = oci_core_network_security_group.gateway[0].id
  source_type               = "NETWORK_SECURITY_GROUP"
  description               = "App traffic from the gateway only"
  tcp_options {
    destination_port_range {
      min = local.app_port
      max = local.app_port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_out" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = local.production_enabled ? "6" : "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  description               = "Sandbox egress; production HTTPS for registry, identity and OCI services"
  dynamic "tcp_options" {
    for_each = local.production_enabled ? [1] : []
    content {
      destination_port_range {
        min = 443
        max = 443
      }
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_out_db" {
  count                     = local.production_enabled ? 1 : 0
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = oci_core_network_security_group.db.id
  destination_type          = "NETWORK_SECURITY_GROUP"
  description               = "PostgreSQL to the app database only"
  tcp_options {
    destination_port_range {
      min = 5432
      max = 5432
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_out_dns_udp" {
  count                     = local.production_enabled ? 1 : 0
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "17"
  destination               = "169.254.169.254/32"
  destination_type          = "CIDR_BLOCK"
  description               = "OCI VCN DNS resolver"
  udp_options {
    destination_port_range {
      min = 53
      max = 53
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_out_dns_tcp" {
  count                     = local.production_enabled ? 1 : 0
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = "169.254.169.254/32"
  destination_type          = "CIDR_BLOCK"
  description               = "OCI VCN DNS resolver TCP fallback"
  tcp_options {
    destination_port_range {
      min = 53
      max = 53
    }
  }
}

resource "oci_core_network_security_group_security_rule" "db_in_app" {
  network_security_group_id = oci_core_network_security_group.db.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = oci_core_network_security_group.app.id
  source_type               = "NETWORK_SECURITY_GROUP"
  description               = "PostgreSQL from the app only"
  tcp_options {
    destination_port_range {
      min = 5432
      max = 5432
    }
  }
}
