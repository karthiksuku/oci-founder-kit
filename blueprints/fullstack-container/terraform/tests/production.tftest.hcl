# Local contract tests use mock providers; they never contact OCI.
mock_provider "oci" {}
mock_provider "oci" {
  alias = "home"
}
mock_provider "random" {}

override_data {
  target = data.oci_identity_availability_domains.ads
  values = {
    availability_domains = [{ name = "test-AD1" }]
  }
}

override_data {
  target = data.oci_psql_db_system_connection_detail.main
  values = {
    primary_db_endpoint = [{ fqdn = "db.example.test", port = 5432 }]
    ca_certificate      = "test CA fixture"
  }
}

override_data {
  target = data.oci_core_services.all
  values = {
    services = [{ id = "ocid1.service.oc1..example", cidr_block = "test-services" }]
  }
}

variables {
  tenancy_ocid          = "ocid1.tenancy.oc1..example"
  compartment_ocid      = "ocid1.compartment.oc1..example"
  region                = "ap-melbourne-1"
  home_region           = "ap-melbourne-1"
  allowed_ingress_cidrs = ["203.0.113.10/32"]
  app_image             = "example.test/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}

run "restricted_sandbox" {
  command = plan
  assert {
    condition     = length(oci_load_balancer_listener.http) == 1 && length(oci_load_balancer_listener.https) == 0
    error_message = "Sandbox must keep its explicit restricted HTTP listener."
  }
  assert {
    condition     = local.app_environment.APP_MODE == "sandbox" && !contains(keys(local.app_environment), "OIDC_CLIENT_SECRET_OCID")
    error_message = "Sandbox must not accidentally enable a partially configured identity flow."
  }
}

run "hardened_contract" {
  command = plan
  variables {
    production = {
      public_origin             = "https://app.example.test"
      oidc_issuer               = "https://identity.example.test"
      oidc_client_id            = "example-client"
      certificate_ocid          = "ocid1.certificate.oc1..example"
      security_compartment_ocid = "ocid1.compartment.oc1..securityexample"
      database_secret_ocid      = "ocid1.vaultsecret.oc1..databaseexample"
      database_secret_version   = 2
      oidc_client_secret_ocid   = "ocid1.vaultsecret.oc1..identityexample"
      session_secret_ocid       = "ocid1.vaultsecret.oc1..sessionexample"
    }
  }
  assert {
    condition     = length(oci_load_balancer_listener.http) == 0 && length(oci_load_balancer_listener.https) == 1 && oci_load_balancer_listener.https[0].port == 443
    error_message = "Production must have HTTPS and no HTTP listener."
  }
  assert {
    condition     = length(oci_core_network_security_group_security_rule.lb_in_http) == 0 && length(oci_core_network_security_group_security_rule.lb_in_https) == 1
    error_message = "Production must only permit the chosen HTTPS ingress ranges."
  }
  assert {
    condition     = oci_load_balancer_listener.https[0].ssl_configuration[0].cipher_suite_name == "oci-tls-12-13-ssl-cipher-suite-v3"
    error_message = "The listener must support its advertised TLS versions and RSA/ECDSA certificates."
  }
  assert {
    condition     = !contains(keys(local.app_environment), "DATABASE_URL") && local.app_environment.DATABASE_PASSWORD_SECRET_VERSION == "2" && local.app_environment.APP_MODE == "production"
    error_message = "Production must inject secret references and bind the database secret version."
  }
  assert {
    condition     = length(random_password.db) == 0 && oci_psql_db_system.main.credentials[0].password_details[0].password_type == "VAULT_SECRET"
    error_message = "Production must not generate or inject a plaintext database password."
  }
  assert {
    condition     = oci_psql_db_system.main.management_policy[0].backup_policy[0].kind == "DAILY" && oci_psql_db_system.main.management_policy[0].backup_policy[0].retention_days == 7
    error_message = "Production must configure its explicit backup policy."
  }
  assert {
    condition     = length(oci_identity_policy.runtime_secrets) == 1 && length(oci_identity_policy.runtime_secrets[0].statements) == 3 && alltrue([for s in oci_identity_policy.runtime_secrets[0].statements : strcontains(s, "to read secret-bundles in compartment id") && strcontains(s, "where target.secret.id =")])
    error_message = "Runtime secret access must be read-only and scoped to each selected secret."
  }
  assert {
    condition     = length(oci_identity_policy.app.statements) == 2 && alltrue([for s in oci_identity_policy.app.statements : !strcontains(s, "PAR_MANAGE")])
    error_message = "Production must not be able to create public pre-authenticated object URLs."
  }
}

run "reject_unsupported_https_port" {
  command = plan
  variables {
    production = {
      public_origin             = "https://app.example.test:8443"
      oidc_issuer               = "https://identity.example.test"
      oidc_client_id            = "example-client"
      certificate_ocid          = "ocid1.certificate.oc1..example"
      security_compartment_ocid = "ocid1.compartment.oc1..securityexample"
      database_secret_ocid      = "ocid1.vaultsecret.oc1..databaseexample"
      database_secret_version   = 1
      oidc_client_secret_ocid   = "ocid1.vaultsecret.oc1..identityexample"
      session_secret_ocid       = "ocid1.vaultsecret.oc1..sessionexample"
    }
  }
  expect_failures = [var.production]
}

run "reject_insecure_production" {
  command = plan
  variables {
    production = {
      public_origin             = "http://app.example.test"
      oidc_issuer               = "https://identity.example.test"
      oidc_client_id            = "example-client"
      certificate_ocid          = "ocid1.certificate.oc1..example"
      security_compartment_ocid = "ocid1.compartment.oc1..securityexample"
      database_secret_ocid      = "ocid1.vaultsecret.oc1..databaseexample"
      database_secret_version   = 1
      oidc_client_secret_ocid   = "ocid1.vaultsecret.oc1..identityexample"
      session_secret_ocid       = "ocid1.vaultsecret.oc1..sessionexample"
    }
  }
  expect_failures = [var.production]
}
