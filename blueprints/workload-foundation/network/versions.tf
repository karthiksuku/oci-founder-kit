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
variable "environment" { type = string }
variable "request_sha256" {
  type = string
  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.request_sha256))
    error_message = "Use the generated foundation proposal binding."
  }
}
variable "name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,24}$", var.name))
    error_message = "Use 3 to 25 lowercase letters, digits and hyphens."
  }
}

variable "compartment_ocid" {
  type = string
  validation {
    condition     = can(regex("^ocid1\\.compartment\\.", var.compartment_ocid))
    error_message = "Select a dedicated non-root compartment."
  }
}
