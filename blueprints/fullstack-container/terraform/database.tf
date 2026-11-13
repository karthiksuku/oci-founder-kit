locals {
  ads         = data.oci_identity_availability_domains.ads.availability_domains
  db_multi_ad = length(local.ads) >= 3
}

resource "random_password" "db" {
  count            = local.production_enabled ? 0 : 1
  length           = 24
  special          = true
  override_special = "#%+-=_"
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2
}

resource "oci_psql_db_system" "main" {
  compartment_id              = var.compartment_ocid
  display_name                = "${var.name}-db"
  db_version                  = var.db_version
  shape                       = var.db_shape
  instance_count              = 1
  instance_ocpu_count         = var.db_ocpus
  instance_memory_size_in_gbs = var.db_memory_gbs

  # Regionally durable storage needs a region with three availability domains;
  # single-AD regions (for example ap-melbourne-1) use storage in their one AD.
  storage_details {
    is_regionally_durable = local.db_multi_ad
    availability_domain   = local.db_multi_ad ? null : local.ads[0].name
    system_type           = "OCI_OPTIMIZED_STORAGE"
  }

  network_details {
    subnet_id = oci_core_subnet.private.id
    nsg_ids   = [oci_core_network_security_group.db.id]
  }

  # Production uses an existing Vault secret without reading its value into state.
  credentials {
    username = "taskboard"
    password_details {
      password_type  = local.production_enabled ? "VAULT_SECRET" : "PLAIN_TEXT"
      password       = local.production_enabled ? null : random_password.db[0].result
      secret_id      = var.production == null ? null : var.production.database_secret_ocid
      secret_version = var.production == null ? null : tostring(var.production.database_secret_version)
    }
  }

  dynamic "management_policy" {
    for_each = local.production_enabled ? [1] : []
    content {
      backup_policy {
        kind           = "DAILY"
        backup_start   = "03:00"
        retention_days = 7
      }
    }
  }
}

data "oci_psql_db_system_connection_detail" "main" {
  db_system_id = oci_psql_db_system.main.id
}
