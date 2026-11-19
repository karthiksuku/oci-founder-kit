variable "tenancy_ocid" {
  description = "Expected account, checked privately against the authenticated administrator."
  type        = string
  validation {
    condition     = can(regex("^ocid1\\.tenancy\\.[a-z0-9_-]+\\.\\.[a-z0-9]+$", var.tenancy_ocid))
    error_message = "Supply the expected tenancy OCID."
  }
}

variable "compartment_ocid" {
  description = "Existing dedicated application compartment; never the tenancy root."
  type        = string
  validation {
    condition     = can(regex("^ocid1\\.compartment\\.[a-z0-9_-]+\\.[a-z0-9_-]*\\.[a-z0-9]+$", var.compartment_ocid))
    error_message = "Select an existing non-root application compartment."
  }
}

variable "state_compartment_ocid" {
  description = "Existing separate state compartment; the state policy is attached here."
  type        = string
  validation {
    condition     = can(regex("^ocid1\\.compartment\\.[a-z0-9_-]+\\.[a-z0-9_-]*\\.[a-z0-9]+$", var.state_compartment_ocid))
    error_message = "Select an existing non-root state compartment."
  }
}

variable "developer_group_ocid" {
  description = "Existing human identity-domain group selected by an authorized administrator. No membership changes."
  type        = string
  validation {
    condition     = can(regex("^ocid1\\.group\\.[a-z0-9_-]+\\.[a-z0-9_-]*\\.[a-z0-9]+$", var.developer_group_ocid))
    error_message = "Supply the selected group OCID, not a name, user or policy fragment."
  }
}

variable "role" {
  description = "Explicit scoped role; runtime IAM and effective access require separate administrator verification."
  type        = string
  validation {
    condition     = contains(["foundation-provisioner", "observer", "app-deployer", "state-operator", "image-publisher"], var.role)
    error_message = "Choose foundation-provisioner, observer, app-deployer, state-operator or image-publisher."
  }
}

variable "name" {
  description = "Policy name prefix unique in both selected compartments."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,24}$", var.name))
    error_message = "Use 3 to 25 lowercase letters, digits and hyphens."
  }
}

variable "registry_name" {
  description = "Exact lowercase repository name; no wildcard. Review case-insensitive name collisions."
  type        = string
  validation {
    condition     = length(var.registry_name) <= 255 && can(regex("^[a-z0-9]+([._/-][a-z0-9]+)*$", var.registry_name))
    error_message = "Use an exact lowercase repository name with no quotes, spaces or wildcards."
  }
}

variable "state_bucket_name" {
  description = "Exact lowercase state bucket name. Content grants depend on the explicit role; bucket deletion is excluded."
  type        = string
  validation {
    condition     = length(var.state_bucket_name) <= 256 && can(regex("^[a-z0-9]+([._-][a-z0-9]+)*$", var.state_bucket_name))
    error_message = "Use an exact lowercase bucket name with no quotes, spaces or wildcards."
  }
}

variable "region" {
  description = "Tenancy home region for these IAM policies; not necessarily the application region."
  type        = string
  validation {
    condition     = can(regex("^[a-z]+-[a-z]+-[0-9]+$", var.region))
    error_message = "Supply the selected IAM region identifier."
  }
}

variable "home_region" {
  description = "Home region independently confirmed by the owner or a successful region-subscription read."
  type        = string
  validation {
    condition     = can(regex("^[a-z]+-[a-z]+-[0-9]+$", var.home_region))
    error_message = "Supply the confirmed home region identifier."
  }
}

variable "config_file_profile" {
  description = "Explicit local administrator profile; configuration and credential files stay outside Git."
  type        = string
  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", var.config_file_profile))
    error_message = "Supply a valid explicit OCI profile name."
  }
}

variable "auth" {
  description = "Authentication used by the reviewed administrator session."
  type        = string
  validation {
    condition     = contains(["APIKey", "SecurityToken"], var.auth)
    error_message = "Choose APIKey or SecurityToken explicitly."
  }
}

variable "state_key" {
  description = "Exact default-workspace state key for state-operator. Only this key and its .lock companion receive content access."
  type        = string
  default     = null
  validation {
    condition     = var.state_key == null ? true : (length(var.state_key) <= 240 && can(regex("^[a-z0-9][a-z0-9._/-]*\\.tfstate$", var.state_key)) && alltrue([for segment in split("/", var.state_key) : segment != "" && segment != "." && segment != ".."]))
    error_message = "Use a lowercase exact relative .tfstate key without empty segments, traversal, quotes or wildcards."
  }
}

variable "certificate_ocid" {
  description = "Existing certificate in the dedicated application compartment for app-deployer; never a key or secret value."
  type        = string
  default     = null
  validation {
    condition     = var.certificate_ocid == null ? true : can(regex("^ocid1\\.certificate\\.[a-z0-9_-]+\\.[a-z0-9_-]+\\.[a-z0-9]+$", var.certificate_ocid))
    error_message = "Select the exact existing certificate OCID in the app compartment."
  }
}

variable "environment" {
  description = "Optional named-environment handoff binding, supplied together with request_sha256 by the foundation helper."
  type        = string
  default     = ""
  validation {
    condition     = var.environment == "" || can(regex("^[a-z][a-z0-9-]{0,39}$", var.environment))
    error_message = "Use a valid explicit environment name or omit the foundation binding."
  }
}

variable "request_sha256" {
  description = "Optional exact foundation request digest; this binding is not cloud authorization."
  type        = string
  default     = ""
  validation {
    condition     = var.request_sha256 == "" || can(regex("^[a-f0-9]{64}$", var.request_sha256))
    error_message = "Use the exact foundation request hash or omit the foundation binding."
  }
}
