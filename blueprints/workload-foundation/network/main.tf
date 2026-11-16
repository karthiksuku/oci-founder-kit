variable "vcn_cidr" {
  type = string
  validation {
    condition     = can(cidrsubnet(var.vcn_cidr, 8, 2)) && endswith(var.vcn_cidr, "/16")
    error_message = "Choose a reviewed nonoverlapping private IPv4 /16."
  }
}
locals {
  public_cidr  = cidrsubnet(var.vcn_cidr, 8, 1)
  private_cidr = cidrsubnet(var.vcn_cidr, 8, 2)
}
data "oci_core_services" "all" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}
resource "oci_core_vcn" "app" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${var.name}-${var.environment}-vcn"
}
resource "oci_core_internet_gateway" "app" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = "${var.name}-${var.environment}-internet"
}
resource "oci_core_nat_gateway" "app" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = "${var.name}-${var.environment}-nat"
}
resource "oci_core_service_gateway" "app" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  services { service_id = data.oci_core_services.all.services[0].id }
}
resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.app.id
  }
}
resource "oci_core_route_table" "private" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_nat_gateway.app.id
  }
  route_rules {
    destination       = data.oci_core_services.all.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.app.id
  }
}
# No default SSH/ingress rules. The reviewed app blueprint adds narrow NSGs.
resource "oci_core_security_list" "empty" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = "${var.name}-${var.environment}-no-rules"
}
resource "oci_core_subnet" "public" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.app.id
  cidr_block                 = local.public_cidr
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.empty.id]
  prohibit_public_ip_on_vnic = false
}
resource "oci_core_subnet" "private" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.app.id
  cidr_block                 = local.private_cidr
  route_table_id             = oci_core_route_table.private.id
  security_list_ids          = [oci_core_security_list.empty.id]
  prohibit_public_ip_on_vnic = true
}
output "foundation" {
  value = {
    schema         = "oci-kit-foundation-output/1"
    component      = "network"
    environment    = var.environment
    request_sha256 = var.request_sha256
    region         = var.region
    target = {
      compartment_id = var.compartment_ocid
      vcn_id         = oci_core_vcn.app.id
      lb_subnet_id   = oci_core_subnet.public.id
      app_subnet_id  = oci_core_subnet.private.id
      app_private_ip = cidrhost(local.private_cidr, 10)
    }
    private = {}
  }
}
