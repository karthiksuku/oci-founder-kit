# Stage 1 of the golden path: a private repository for the app image, in the
# workload compartment. Push the image here before applying ../terraform.
terraform {
  required_version = ">= 1.6"
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

variable "compartment_ocid" {
  description = "Compartment for the repository. Never the root compartment."
  type        = string
  validation {
    condition     = can(regex("^ocid1\\.compartment\\.", var.compartment_ocid))
    error_message = "compartment_ocid must be a compartment OCID, not the tenancy (root) OCID."
  }
}

variable "region" {
  type = string
}

variable "config_file_profile" {
  type    = string
  default = "DEFAULT"
}

variable "name" {
  description = "Repository name; must match the image name and the main stack's name."
  type        = string
  default     = "taskboard"
}

variable "immutable_tags" {
  description = "Leave false for digest-only publication. Legacy tagged publication requires verified immutable tags; support for enabling this flag is service-dependent."
  type        = bool
  default     = false
}

data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.compartment_ocid
}

data "oci_identity_regions" "all" {}

locals {
  region_key = lower([for r in data.oci_identity_regions.all.regions : r.key if r.name == var.region][0])
}

resource "oci_artifacts_container_repository" "app" {
  compartment_id = var.compartment_ocid
  display_name   = var.name
  is_public      = false
  # Digest-only publication does not assign or overwrite a tag.
  is_immutable = var.immutable_tags
}

output "image_repository" {
  description = "Destination for the image approval gate. Deploy only its verified <repository>@sha256:<digest> receipt."
  value       = "${local.region_key}.ocir.io/${data.oci_objectstorage_namespace.ns.namespace}/${oci_artifacts_container_repository.app.display_name}"
}

variable "tenancy_ocid" {
  description = "Expected tenancy, matching the privately configured deployment identity."
  type        = string
  validation {
    condition     = can(regex("^ocid1\\.tenancy\\.[a-z0-9-]+\\.\\.[a-z0-9]+$", var.tenancy_ocid))
    error_message = "Supply the expected tenancy OCID."
  }
}

variable "auth" {
  type    = string
  default = "APIKey"
  validation {
    condition     = contains(["APIKey", "SecurityToken", "InstancePrincipal", "ResourcePrincipal"], var.auth)
    error_message = "Choose the authentication mode matching the readiness check."
  }
}
