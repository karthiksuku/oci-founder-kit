# Opt-in hardened configuration. These are identifiers and public URLs, never
# secret values. Prepare them privately before planning; see ../PRODUCTION.md.
variable "production" {
  description = "Explicit HTTPS/OIDC/Vault inputs. Null keeps the restricted sandbox. Secrets and certificate must exist in the selected security compartment."
  type = object({
    public_origin             = string
    oidc_issuer               = string
    oidc_client_id            = string
    certificate_ocid          = string
    security_compartment_ocid = string
    database_secret_ocid      = string
    database_secret_version   = number
    oidc_client_secret_ocid   = string
    session_secret_ocid       = string
  })
  default = null
  validation {
    condition = var.production == null ? true : (
      can(regex("^https://[A-Za-z0-9.-]+(:443)?$", var.production.public_origin)) &&
      can(regex("^https://[A-Za-z0-9.-]+(:[0-9]+)?(/[^?#]*)?$", var.production.oidc_issuer)) &&
      length(trimspace(var.production.oidc_client_id)) > 0 &&
      can(regex("^ocid1\\.certificate\\.", var.production.certificate_ocid)) &&
      can(regex("^ocid1\\.compartment\\.", var.production.security_compartment_ocid)) &&
      alltrue([for id in [var.production.database_secret_ocid, var.production.oidc_client_secret_ocid, var.production.session_secret_ocid] : can(regex("^ocid1\\.vaultsecret\\.", id))]) &&
      length(distinct([var.production.database_secret_ocid, var.production.oidc_client_secret_ocid, var.production.session_secret_ocid])) == 3 &&
      var.production.database_secret_version >= 1 && floor(var.production.database_secret_version) == var.production.database_secret_version
    )
    error_message = "Production requires an HTTPS origin on port 443, an HTTPS OIDC issuer and client, a certificate, non-root security compartment, three distinct Vault secret IDs and a positive integer database secret version."
  }
}

locals {
  production_enabled = var.production != null
  production_secrets = var.production == null ? [] : [
    var.production.database_secret_ocid,
    var.production.oidc_client_secret_ocid,
    var.production.session_secret_ocid,
  ]
}

resource "oci_identity_policy" "runtime_secrets" {
  count          = local.production_enabled ? 1 : 0
  provider       = oci.home
  compartment_id = var.production.security_compartment_ocid
  name           = "${var.name}-runtime-secrets"
  description    = "Read only the three runtime secret bundles for this app"
  statements = [for id in local.production_secrets :
    "Allow dynamic-group ${oci_identity_dynamic_group.app.name} to read secret-bundles in compartment id ${var.production.security_compartment_ocid} where target.secret.id = '${id}'"
  ]
}

# Preserve existing sandbox resource addresses when upgrading the kit.
moved {
  from = random_password.db
  to   = random_password.db[0]
}

moved {
  from = oci_load_balancer_listener.http
  to   = oci_load_balancer_listener.http[0]
}
