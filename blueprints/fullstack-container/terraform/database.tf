resource "random_password" "db" {
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

  storage_details {
    is_regionally_durable = true
    system_type           = "OCI_OPTIMIZED_STORAGE"
  }

  network_details {
    subnet_id = oci_core_subnet.private.id
    nsg_ids   = [oci_core_network_security_group.db.id]
  }

  # Sandbox default: the password is generated here and kept in Terraform state.
  # For production, store it in OCI Vault and use password_type = "VAULT_SECRET".
  credentials {
    username = "taskboard"
    password_details {
      password_type = "PLAIN_TEXT"
      password      = random_password.db.result
    }
  }
}

data "oci_psql_db_system_connection_detail" "main" {
  db_system_id = oci_psql_db_system.main.id
}
