mock_provider "oci" {}
variables {
  region               = "us-phoenix-1"
  config_file_profile  = "SYNTHETIC"
  tenancy_ocid         = "ocid1.tenancy.oc1..synthetictenancy"
  auth                 = "SecurityToken"
  environment          = "rehearsal"
  request_sha256       = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  name                 = "founder"
  compartment_ocid     = "ocid1.compartment.oc1..syntheticcompartment"
  namespace            = "syntheticnamespace"
  state_key            = "rehearsal/main.tfstate"
  workspace_key_prefix = "rehearsal/workspaces"
}
run "scoped_foundation_plan" {
  command = plan
  assert {
    condition     = oci_objectstorage_bucket.state.access_type == "NoPublicAccess"
    error_message = "Foundation isolation contract changed."
  }
  assert {
    condition     = oci_objectstorage_bucket.state.versioning == "Enabled"
    error_message = "Foundation isolation contract changed."
  }
  assert {
    condition     = output.foundation.request_sha256 == var.request_sha256 && output.foundation.environment == var.environment
    error_message = "Output must bind the exact local proposal and environment."
  }
}
