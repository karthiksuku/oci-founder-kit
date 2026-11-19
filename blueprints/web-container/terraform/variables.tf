variable "tenancy_ocid" {
  type        = string
  description = "Tenancy containing the dedicated workload compartment. Credentials stay outside Terraform."
  validation {
    condition     = can(regex("^ocid1\\.tenancy\\.[A-Za-z0-9.]+$", var.tenancy_ocid))
    error_message = "Use a tenancy OCID."
  }
}

variable "compartment_ocid" {
  type        = string
  description = "Dedicated environment compartment; never the tenancy root or a shared application compartment."
  validation {
    condition     = can(regex("^ocid1\\.compartment\\.[A-Za-z0-9.]+$", var.compartment_ocid))
    error_message = "Use a non-root compartment OCID."
  }
}

variable "region" {
  type = string
}

variable "home_region" {
  type        = string
  description = "Tenancy home region, used only when manage_runtime_iam is enabled."
}

variable "config_file_profile" {
  type    = string
  default = "DEFAULT"
}

variable "auth" {
  type    = string
  default = "SecurityToken"
  validation {
    condition     = contains(["APIKey", "SecurityToken", "InstancePrincipal", "ResourcePrincipal"], var.auth)
    error_message = "Choose a supported OCI provider authentication mode."
  }
}

variable "name" {
  type    = string
  default = "founder-web"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.name))
    error_message = "Use 3 to 31 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "availability_domain" {
  type        = string
  description = "Explicit AD verified for this region and Container Instances shape; limits do not prove capacity."
}

variable "network" {
  description = "Reviewed existing network. This target creates NSGs but does not change subnet security lists, routing or gateways."
  type = object({
    vcn_ocid            = string
    public_subnet_ocid  = string
    private_subnet_ocid = string
    app_private_ip      = string
  })
  validation {
    condition = (
      can(regex("^ocid1\\.vcn\\.[A-Za-z0-9.]+$", var.network.vcn_ocid)) &&
      alltrue([for id in [var.network.public_subnet_ocid, var.network.private_subnet_ocid] : can(regex("^ocid1\\.subnet\\.[A-Za-z0-9.]+$", id))]) &&
      var.network.public_subnet_ocid != var.network.private_subnet_ocid &&
      can(cidrhost("${var.network.app_private_ip}/32", 0)) && !strcontains(var.network.app_private_ip, ":")
    )
    error_message = "Use one VCN, distinct public/private subnet OCIDs and an available private IPv4 address."
  }
}

variable "allowed_ingress_cidrs" {
  type        = set(string)
  description = "Explicit allowed HTTPS client ranges. Begin rehearsal with tester /32 addresses."
  validation {
    condition     = length(var.allowed_ingress_cidrs) > 0 && alltrue([for c in var.allowed_ingress_cidrs : can(cidrhost(c, 0)) && !strcontains(c, ":")])
    error_message = "Select at least one IPv4 client CIDR."
  }
}

variable "certificate_ocid" {
  type        = string
  description = "Existing OCI Certificates certificate valid for public_origin; no private key enters Terraform."
  validation {
    condition     = can(regex("^ocid1\\.certificate\\.[A-Za-z0-9.]+$", var.certificate_ocid))
    error_message = "Select an existing certificate OCID."
  }
}

variable "public_origin" {
  type        = string
  description = "HTTPS hostname for this environment, with matching certificate and separately reviewed DNS."
  validation {
    condition     = can(regex("^https://[A-Za-z0-9][A-Za-z0-9.-]*(:443)?$", var.public_origin))
    error_message = "Use an HTTPS origin on port 443 without path, credentials or query."
  }
}

variable "app_image" {
  type        = string
  description = "Verified Linux amd64 image in the selected private OCIR repository, pinned to its published digest."
  validation {
    condition     = can(regex("^[a-z0-9.-]+\\.ocir\\.io/[a-z0-9_-]+/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$", var.app_image))
    error_message = "Use the private OCIR image URI with an immutable sha256 digest."
  }
}

variable "registry" {
  type = object({
    compartment_ocid = string
    repository_name  = string
  })
  description = "Existing private repository created and populated through the registry/image gates."
  validation {
    condition     = can(regex("^ocid1\\.compartment\\.[A-Za-z0-9.]+$", var.registry.compartment_ocid)) && can(regex("^[a-z0-9]+(?:[._/-][a-z0-9]+)*$", var.registry.repository_name))
    error_message = "Use a non-root registry compartment and an OCI repository name."
  }
}

variable "app_port" {
  type    = number
  default = 8080
  validation {
    condition     = var.app_port >= 1024 && var.app_port <= 65535 && floor(var.app_port) == var.app_port
    error_message = "Use an unprivileged integer port between 1024 and 65535."
  }
}

variable "health_path" {
  type    = string
  default = "/healthz"
  validation {
    condition     = can(regex("^/[A-Za-z0-9/_.-]*$", var.health_path)) && length(var.health_path) <= 200
    error_message = "Use a path without credentials, query parameters or fragments."
  }
}

variable "app_ocpus" {
  type    = number
  default = 1
  validation {
    condition     = var.app_ocpus >= 1 && var.app_ocpus <= 64 && floor(var.app_ocpus) == var.app_ocpus
    error_message = "Use 1 to 64 whole OCPUs, after reviewing limits and costs."
  }
}

variable "app_memory_gbs" {
  type    = number
  default = 4
  validation {
    condition     = var.app_memory_gbs >= 1 && var.app_memory_gbs <= 1024 && floor(var.app_memory_gbs) == var.app_memory_gbs
    error_message = "Use whole GiB, within the selected shape's OCPU-to-memory limits."
  }
}

variable "public_environment" {
  type        = map(string)
  default     = {}
  description = "Reviewed NONSECRET app settings. Values enter Terraform state and OCI metadata. Never place passwords, tokens, connection strings or private keys here."
  validation {
    condition = alltrue([for key, value in var.public_environment :
      can(regex("^[A-Z][A-Z0-9_]{0,63}$", key)) &&
      !can(regex("SECRET|PASSWORD|TOKEN|CREDENTIAL|KEY|AUTHORIZATION|DATABASE_URL|CONNECTION_STRING|^OCI_|^HOST$|^PORT$|^PUBLIC_ORIGIN$", key)) &&
      length(value) <= 2048 && !can(regex("[\\r\\n]|://[^/]*@|-----BEGIN", value))
    ])
    error_message = "Environment entries must be reviewed nonsecret settings; reserved names and likely credentials are refused."
  }
}

variable "secret_references" {
  type = map(object({
    secret_ocid      = string
    compartment_ocid = string
  }))
  default     = {}
  description = "App-specific *_SECRET_OCID names mapped to existing Vault secret identifiers, never secret values. The image must implement resource-principal retrieval."
  validation {
    condition = alltrue([for key, ref in var.secret_references :
      can(regex("^[A-Z][A-Z0-9_]*_SECRET_OCID$", key)) && !startswith(key, "OCI_") &&
      can(regex("^ocid1\\.vaultsecret\\.[A-Za-z0-9.]+$", ref.secret_ocid)) &&
      can(regex("^ocid1\\.compartment\\.[A-Za-z0-9.]+$", ref.compartment_ocid))
    ]) && length(var.secret_references) <= 16
    error_message = "Use at most 16 named Vault references in non-root secret compartments."
  }
}

variable "dependency_egress" {
  type = map(object({
    destination_cidr = string
    port             = number
  }))
  default     = {}
  description = "Additional reviewed TLS dependency destinations, for example retained PostgreSQL /32 on 5432. HTTPS and OCI DNS have separate rules. Never grants all ports."
  validation {
    condition = alltrue([for name, rule in var.dependency_egress :
      can(regex("^[a-z][a-z0-9-]{0,40}$", name)) && can(cidrhost(rule.destination_cidr, 0)) &&
      !strcontains(rule.destination_cidr, ":") && !contains(["0.0.0.0/0", "0.0.0.0/1", "128.0.0.0/1"], rule.destination_cidr) &&
      rule.port >= 1 && rule.port <= 65535 && floor(rule.port) == rule.port
    ]) && length(var.dependency_egress) <= 16
    error_message = "Select bounded IPv4 destinations and individual ports; verify TLS in the app separately."
  }
}

variable "application_contract" {
  type = object({
    evidence_sha256                = string
    background_work                = string
    background_control_environment = optional(map(string), {})
    vault_references_implemented   = optional(bool, false)
  })
  default = {
    evidence_sha256 = ""
    background_work = "unverified"
  }
  description = "Owner-reviewed local evidence for this exact image: jobs absent or disabled and secret adapter tested. This declaration is not independent runtime verification."
  validation {
    condition = (contains(["unverified", "absent", "disabled"], var.application_contract.background_work) &&
      alltrue([for key, value in var.application_contract.background_control_environment :
        can(regex("^[A-Z][A-Z0-9_]{0,63}$", key)) &&
        !can(regex("SECRET|PASSWORD|TOKEN|CREDENTIAL|KEY|^OCI_|^HOST$|^PORT$|^PUBLIC_ORIGIN$", key)) &&
        contains(["false", "0", "off", "disabled", "web"], value)
    ]))
    error_message = "Only absent or explicitly disabled background work is supported; controls must be nonsecret disable settings understood by the image."
  }
}

variable "manage_runtime_iam" {
  type        = bool
  default     = false
  description = "False reuses separately reviewed existing policies. True includes dynamic group and scoped registry/Vault policies in this plan, requiring exact IAM approval."
}
