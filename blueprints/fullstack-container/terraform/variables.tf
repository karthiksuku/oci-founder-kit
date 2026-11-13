variable "tenancy_ocid" {
  description = "Tenancy OCID; dynamic groups live in the tenancy root."
  type        = string
}

variable "compartment_ocid" {
  description = "Compartment for every workload resource. Never the root compartment."
  type        = string
  validation {
    condition     = can(regex("^ocid1\\.compartment\\.", var.compartment_ocid))
    error_message = "compartment_ocid must be a compartment OCID, not the tenancy (root) OCID."
  }
}

variable "region" {
  description = "Region for the workload, for example ap-melbourne-1."
  type        = string
}

variable "home_region" {
  description = "The tenancy's home region, where IAM changes are made."
  type        = string
}

variable "config_file_profile" {
  description = "Profile in ~/.oci/config used by Terraform."
  type        = string
  default     = "DEFAULT"
}

variable "name" {
  description = "Prefix for resource names."
  type        = string
  default     = "taskboard"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,20}$", var.name))
    error_message = "name must be 3 to 21 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "allowed_ingress_cidrs" {
  description = "CIDRs allowed to reach the load balancer. No default: choose who can reach the app."
  type        = list(string)
  validation {
    condition     = length(var.allowed_ingress_cidrs) > 0 && alltrue([for c in var.allowed_ingress_cidrs : can(cidrhost(c, 0))])
    error_message = "allowed_ingress_cidrs must list at least one valid CIDR."
  }
}

variable "app_image" {
  description = "Container image for the app, for example <region-key>.ocir.io/<namespace>/taskboard:0.1.0."
  type        = string
}

variable "app_ocpus" {
  type    = number
  default = 1
}

variable "app_memory_gbs" {
  type    = number
  default = 4
}

variable "db_version" {
  description = "PostgreSQL major version supported by the chosen shape in the region."
  type        = string
  default     = "16"
}

variable "db_shape" {
  type    = string
  default = "VM.Standard.E5.Flex"
}

variable "db_ocpus" {
  type    = number
  default = 2
}

variable "db_memory_gbs" {
  type    = number
  default = 32
}

variable "vcn_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "alert_email" {
  description = "Email for alarm notifications. Empty means no subscription (the topic still exists)."
  type        = string
  default     = ""
}

variable "auth" {
  description = "Authentication mode selected during OCI readiness; credentials remain outside Terraform."
  type        = string
  default     = "APIKey"
  validation {
    condition     = contains(["APIKey", "SecurityToken", "InstancePrincipal", "ResourcePrincipal"], var.auth)
    error_message = "Choose the OCI provider authentication mode matching the readiness check."
  }
}
