mock_provider "oci" {}
override_data {
  target = data.oci_core_services.all
  values = {
    services = [{ id = "ocid1.service.oc1.phx.synthetic", cidr_block = "all-phx-services-in-oracle-services-network" }]
  }
}
variables {
  region              = "us-phoenix-1"
  config_file_profile = "SYNTHETIC"
  tenancy_ocid        = "ocid1.tenancy.oc1..synthetictenancy"
  auth                = "SecurityToken"
  environment         = "rehearsal"
  request_sha256      = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  name                = "founder"
  compartment_ocid    = "ocid1.compartment.oc1..syntheticcompartment"
  vcn_cidr            = "10.88.0.0/16"
}
run "scoped_foundation_plan" {
  command = plan
  assert {
    condition     = oci_core_subnet.private.prohibit_public_ip_on_vnic == true
    error_message = "Foundation isolation contract changed."
  }
  assert {
    condition     = oci_core_subnet.public.prohibit_public_ip_on_vnic == false
    error_message = "Foundation isolation contract changed."
  }
  assert {
    condition     = length(oci_core_security_list.empty.ingress_security_rules) == 0
    error_message = "Foundation isolation contract changed."
  }
  assert {
    condition     = output.foundation.request_sha256 == var.request_sha256 && output.foundation.environment == var.environment
    error_message = "Output must bind the exact local proposal and environment."
  }
}
