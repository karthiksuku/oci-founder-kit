terraform {
  required_version = ">= 1.7"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.10.0"
    }
  }
}
provider "oci" {
  region              = var.region
  config_file_profile = var.config_file_profile
  tenancy_ocid        = var.tenancy_ocid
  auth                = var.auth
}
variable "region" { type = string }
variable "config_file_profile" { type = string }
variable "tenancy_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1\\.tenancy\\.", var.tenancy_ocid))
    error_message = "Select the expected tenancy."
  }
}
variable "auth" {
  type = string
  validation {
    condition     = contains(["APIKey", "SecurityToken"], var.auth)
    error_message = "Select APIKey or SecurityToken authentication."
  }
}
