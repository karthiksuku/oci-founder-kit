variable "tenancy_ocid" {
  description = "Explicit expected account identity, matching the authenticated OCI profile. Not the resource target compartment."
  type        = string
  validation {
    condition     = can(regex("^ocid1\\.tenancy\\.[a-z0-9-]+\\.[a-z0-9-]*\\.[a-z0-9]+$", var.tenancy_ocid))
    error_message = "Supply the expected tenancy OCID, confirmed against the authenticated identity."
  }
}

variable "compartment_ocid" {
  description = "Existing non-root parent compartment. The child is created underneath it."
  type        = string
  validation {
    condition     = can(regex("^ocid1\\.compartment\\.[a-z0-9-]+\\.[a-z0-9-]*\\.[a-z0-9]+$", var.compartment_ocid))
    error_message = "Select an existing non-root compartment OCID; tenancy/root identifiers are refused."
  }
}

variable "developer_group_ocid" {
  description = "Existing group OCID, confirmed by the administrator in this tenancy."
  type        = string
  validation {
    condition     = can(regex("^ocid1\\.group\\.[a-z0-9-]+\\.[a-z0-9-]*\\.[a-z0-9]+$", var.developer_group_ocid))
    error_message = "Supply a group OCID, not a name, user OCID or policy fragment."
  }
}

variable "workload_name" {
  description = "Unique child compartment name within the selected parent."
  type        = string
  validation {
    condition     = can(regex("^[A-Za-z][A-Za-z0-9_-]{0,62}$", var.workload_name))
    error_message = "Use a letter followed by up to 62 letters, digits, hyphens or underscores."
  }
}

variable "region" {
  description = "Tenancy home region for IAM writes; verify it with the account owner."
  type        = string
  validation {
    condition     = can(regex("^[a-z]+-[a-z]+-[0-9]+$", var.region))
    error_message = "Supply the tenancy home region identifier."
  }
}

variable "config_file_profile" {
  description = "Private OCI configuration profile used by readiness and deployment."
  type        = string
  default     = "DEFAULT"
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+$", var.config_file_profile))
    error_message = "Use a profile name containing only letters, digits, underscores or hyphens."
  }
}

variable "auth" {
  description = "OCI provider authentication method; credentials stay outside this stack."
  type        = string
  default     = "APIKey"
  validation {
    condition     = contains(["APIKey", "SecurityToken", "InstancePrincipal", "ResourcePrincipal"], var.auth)
    error_message = "Use APIKey, SecurityToken, InstancePrincipal or ResourcePrincipal."
  }
}
