variable "region" { type = string }
variable "home_region" { type = string }
variable "tenancy_ocid" { type = string }
variable "config_file_profile" { type = string }
variable "auth" {
  type = string
  validation {
    condition     = contains(["APIKey", "SecurityToken"], var.auth)
    error_message = "Select an explicit supported operator authentication mode."
  }
}
variable "name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,39}$", var.name))
    error_message = "Use a bounded lowercase environment name."
  }
}
variable "compartment_ocid" { type = string }
variable "web_compartment_ocid" { type = string }
variable "availability_domain" { type = string }
variable "app_image" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9.-]+\\.ocir\\.io/[^@\\s]+@sha256:[0-9a-f]{64}$", var.app_image))
    error_message = "Use the worker's verified immutable OCIR digest."
  }
}
variable "app_ocpus" {
  type    = number
  default = 1
}
variable "app_memory_gbs" {
  type    = number
  default = 4
}
variable "network" {
  type = object({ vcn_ocid = string, private_subnet_ocid = string, app_private_ip = string })
}
variable "egress" {
  description = "Reviewed destination CIDRs/ports for PostgreSQL, DNS, Queue, Vault and image pull; no ingress is created. Review inherited subnet security separately."
  type        = map(object({ cidr = string, protocol = string, port = number }))
  validation {
    condition     = alltrue([for rule in values(var.egress) : can(cidrhost(rule.cidr, 0)) && contains(["6", "17"], rule.protocol) && rule.port >= 1 && rule.port <= 65535 && rule.port == floor(rule.port)])
    error_message = "Egress needs reviewed CIDRs and exact TCP or UDP ports."
  }
}
variable "registry" {
  type = object({ compartment_ocid = string, repository_name = string })
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9._/-]{0,200}$", var.registry.repository_name))
    error_message = "Invalid repository name."
  }
}
variable "secret_references" {
  type = map(object({ secret_ocid = string, compartment_ocid = string }))
  validation {
    condition     = (toset(keys(var.secret_references)) == toset(["DATABASE_PASSWORD_SECRET_OCID"]) && alltrue([for ref in values(var.secret_references) : can(regex("^ocid1\\.vaultsecret\\.[a-z0-9.-]+$", ref.secret_ocid)) && can(regex("^ocid1\\.compartment\\.[a-z0-9.-]+$", ref.compartment_ocid))]))
    error_message = "The worker can read only its dedicated database credential reference."
  }
}
variable "public_environment" {
  description = "Nonsecret database coordinates and public CA; never a password, URL with credentials or OIDC/session secret."
  type        = map(string)
  validation {
    condition     = (length(setsubtract(toset(keys(var.public_environment)), toset(["DATABASE_HOST", "DATABASE_NAME", "DATABASE_USER", "DATABASE_CA_CERT"]))) == 0 && length(var.public_environment) == 4)
    error_message = "Only the four required nonsecret worker database settings are accepted."
  }
}
variable "manage_runtime_iam" {
  type    = bool
  default = false
}
