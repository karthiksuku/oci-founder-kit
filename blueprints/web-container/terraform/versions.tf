terraform {
  required_version = ">= 1.7"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 9.10"
    }
  }
}

provider "oci" {
  region              = var.region
  config_file_profile = var.config_file_profile
  tenancy_ocid        = var.tenancy_ocid
  auth                = var.auth
}

provider "oci" {
  alias               = "home"
  region              = var.home_region
  config_file_profile = var.config_file_profile
  tenancy_ocid        = var.tenancy_ocid
  auth                = var.auth
}
