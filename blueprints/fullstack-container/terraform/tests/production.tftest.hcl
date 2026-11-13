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
    condition     = var.ingress_mode == "load_balancer" && length(oci_apigateway_gateway.web) == 0 && length(oci_load_balancer_load_balancer.web) == 1
    error_message = "The default must retain the load balancer and create no gateway."
  }
  assert {
    condition     = length(oci_load_balancer_listener.http) == 1 && length(oci_load_balancer_listener.https) == 0
    error_message = "Sandbox must keep its explicit restricted HTTP listener."
  }
  assert {
    condition     = local.app_environment.APP_MODE == "sandbox" && !contains(keys(local.app_environment), "OIDC_CLIENT_SECRET_OCID")
    error_message = "Sandbox must not accidentally enable a partially configured identity flow."
  }
}

run "gateway_bootstrap" {
  command = plan
  plan_options {
    target = [oci_apigateway_gateway.web]
  }
  variables {
    ingress_mode = "api_gateway"
  }
  assert {
    condition     = var.production == null && oci_apigateway_gateway.web[0].endpoint_type == "PUBLIC"
    error_message = "Only the gateway/network bootstrap may precede the identity configuration."
  }
  assert {
    condition     = length(oci_core_network_security_group_security_rule.gateway_in_https) == 1 && oci_core_network_security_group_security_rule.gateway_in_https["203.0.113.10/32"].tcp_options[0].destination_port_range[0].min == 443 && length(oci_core_network_security_group_security_rule.gateway_out_app) == 1 && length(oci_core_network_security_group_security_rule.app_in_gateway) == 1
    error_message = "A targeted gateway bootstrap must include the restrictive ingress and private-backend rules."
  }
}

run "managed_gateway_contract" {
  # Mock apply resolves computed hostnames and resource IDs without calling OCI.
  command = apply
  variables {
    ingress_mode = "api_gateway"
    production = {
      oidc_issuer               = "https://identity.example.test"
      oidc_discovery_url        = "https://tenant.example.test/.well-known/openid-configuration"
      oidc_client_id            = "example-client"
      security_compartment_ocid = "ocid1.compartment.oc1..securityexample"
      database_secret_ocid      = "ocid1.vaultsecret.oc1..databaseexample"
      database_secret_version   = 2
      oidc_client_secret_ocid   = "ocid1.vaultsecret.oc1..identityexample"
      session_secret_ocid       = "ocid1.vaultsecret.oc1..sessionexample"
    }
  }
  assert {
    condition     = length(oci_load_balancer_load_balancer.web) == 0 && length(oci_load_balancer_listener.http) == 0 && length(oci_load_balancer_listener.https) == 0 && length(oci_core_subnet.public) == 0 && length(oci_core_network_security_group.lb) == 0
    error_message = "Gateway mode must not retain a load balancer or its alternate ingress."
  }
  assert {
    condition     = length(oci_monitoring_alarm.unhealthy_backend) == 0 && length(oci_ons_notification_topic.alerts) == 0 && output.load_balancer_ip == null
    error_message = "Gateway mode must not claim load-balancer monitoring or outputs."
  }
  assert {
    condition     = var.production.public_origin == null && var.production.certificate_ocid == null && local.app_environment.PUBLIC_ORIGIN == "https://${oci_apigateway_gateway.web[0].hostname}" && output.app_url == local.app_environment.PUBLIC_ORIGIN
    error_message = "The origin must use the actual managed gateway hostname with no invented hostname/certificate."
  }
  assert {
    condition     = local.app_environment.APP_MODE == "production" && local.app_environment.TRUST_PROXY_CIDRS == oci_core_subnet.gateway[0].cidr_block && !contains(keys(local.app_environment), "DATABASE_URL") && length(random_password.db) == 0 && local.app_environment.OIDC_ISSUER == var.production.oidc_issuer && local.app_environment.OIDC_DISCOVERY_URL == var.production.oidc_discovery_url
    error_message = "The gateway must preserve hardened authentication/secrets and trust only its own proxy subnet."
  }
  assert {
    condition     = oci_core_subnet.gateway[0].cidr_block != oci_core_subnet.private.cidr_block && oci_core_subnet.private.prohibit_public_ip_on_vnic && !oci_container_instances_container_instance.app.vnics[0].is_public_ip_assigned && length(oci_core_security_list.none.ingress_security_rules) == 0 && length(oci_core_network_security_group_security_rule.app_in_lb) == 0
    error_message = "The gateway subnet must be separate and the app must have no public or alternate ingress."
  }
  assert {
    condition     = oci_core_network_security_group_security_rule.app_in_gateway[0].source_type == "NETWORK_SECURITY_GROUP" && oci_core_network_security_group_security_rule.app_in_gateway[0].source == oci_core_network_security_group.gateway[0].id && oci_core_network_security_group_security_rule.gateway_out_app[0].destination == oci_core_network_security_group.app.id && oci_core_network_security_group_security_rule.gateway_out_app[0].tcp_options[0].destination_port_range[0].max == 8080
    error_message = "Only the gateway NSG may reach the private application port."
  }
  assert {
    condition     = oci_apigateway_deployment.app[0].path_prefix == "/" && oci_apigateway_deployment.app[0].specification[0].routes[0].path == "/{path*}" && oci_apigateway_deployment.app[0].specification[0].routes[0].backend[0].url == "http://${local.app_private_ip}:8080/$${request.path[path]}" && toset(oci_apigateway_deployment.app[0].specification[0].routes[0].methods) == toset(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    error_message = "Root, nested static/API/auth paths and binary upload methods must route to the fixed private backend."
  }
  assert {
    condition     = oci_apigateway_deployment.app[0].specification[0].routes[0].request_policies[0].header_transformations[0].set_headers[0].items[0].name == "X-Forwarded-Proto" && oci_apigateway_deployment.app[0].specification[0].routes[0].request_policies[0].header_transformations[0].set_headers[0].items[0].if_exists == "OVERWRITE" && oci_apigateway_deployment.app[0].specification[0].routes[0].request_policies[0].header_transformations[0].set_headers[0].items[0].values[0] == "https"
    error_message = "An untrusted forwarded protocol must be overwritten before the app trusts the gateway."
  }
  assert {
    condition     = !oci_apigateway_deployment.app[0].specification[0].logging_policies[0].access_log[0].is_enabled && !oci_apigateway_deployment.app[0].specification[0].logging_policies[0].execution_log[0].is_enabled && length(oci_apigateway_gateway.web[0].response_cache_details) == 0 && length(oci_apigateway_deployment.app[0].specification[0].routes[0].request_policies[0].response_cache_lookup) == 0 && length(oci_apigateway_deployment.app[0].specification[0].routes[0].request_policies[0].query_parameter_transformations) == 0 && length(oci_apigateway_deployment.app[0].specification[0].routes[0].response_policies) == 0
    error_message = "The gateway must not cache authenticated responses, log callbacks, or transform callback queries/cookies."
  }
}

run "reject_unauthenticated_gateway_app" {
  command = plan
  variables {
    ingress_mode = "api_gateway"
  }
  expect_failures = [oci_container_instances_container_instance.app]
}

run "reject_broad_gateway_ingress" {
  command = plan
  plan_options {
    target = [oci_apigateway_gateway.web]
  }
  variables {
    ingress_mode          = "api_gateway"
    allowed_ingress_cidrs = ["203.0.113.0/24"]
  }
  expect_failures = [oci_apigateway_gateway.web]
}

run "reject_small_gateway_subnet" {
  command = plan
  plan_options {
    target = [oci_apigateway_gateway.web]
  }
  variables {
    ingress_mode = "api_gateway"
    vcn_cidr     = "10.20.0.0/20"
  }
  expect_failures = [oci_apigateway_gateway.web]
}

run "reject_unknown_ingress_mode" {
  command = plan
  variables {
    ingress_mode = "other"
  }
  expect_failures = [var.ingress_mode]
}

run "reject_missing_load_balancer_certificate" {
  command = plan
  variables {
    production = {
      public_origin             = "https://app.example.test"
      oidc_issuer               = "https://identity.example.test"
      oidc_client_id            = "example-client"
      security_compartment_ocid = "ocid1.compartment.oc1..securityexample"
      database_secret_ocid      = "ocid1.vaultsecret.oc1..databaseexample"
      database_secret_version   = 1
      oidc_client_secret_ocid   = "ocid1.vaultsecret.oc1..identityexample"
      session_secret_ocid       = "ocid1.vaultsecret.oc1..sessionexample"
    }
  }
  expect_failures = [oci_load_balancer_load_balancer.web]
}

run "reject_missing_load_balancer_origin" {
  command = plan
  variables {
    production = {
      certificate_ocid          = "ocid1.certificate.oc1..example"
      oidc_issuer               = "https://identity.example.test"
      oidc_client_id            = "example-client"
      security_compartment_ocid = "ocid1.compartment.oc1..securityexample"
      database_secret_ocid      = "ocid1.vaultsecret.oc1..databaseexample"
      database_secret_version   = 1
      oidc_client_secret_ocid   = "ocid1.vaultsecret.oc1..identityexample"
      session_secret_ocid       = "ocid1.vaultsecret.oc1..sessionexample"
    }
  }
  expect_failures = [oci_load_balancer_load_balancer.web]
}

run "reject_gateway_origin_override" {
  command = plan
  plan_options {
    target = [oci_apigateway_gateway.web]
  }
  variables {
    ingress_mode = "api_gateway"
    production = {
      public_origin             = "https://invented.example.test"
      oidc_issuer               = "https://identity.example.test"
      oidc_client_id            = "example-client"
      security_compartment_ocid = "ocid1.compartment.oc1..securityexample"
      database_secret_ocid      = "ocid1.vaultsecret.oc1..databaseexample"
      database_secret_version   = 1
      oidc_client_secret_ocid   = "ocid1.vaultsecret.oc1..identityexample"
      session_secret_ocid       = "ocid1.vaultsecret.oc1..sessionexample"
    }
  }
  expect_failures = [oci_apigateway_gateway.web]
}

run "reject_insecure_discovery_document" {
  command = plan
  variables {
    production = {
      public_origin             = "https://app.example.test"
      certificate_ocid          = "ocid1.certificate.oc1..example"
      oidc_issuer               = "https://identity.example.test"
      oidc_discovery_url        = "http://tenant.example.test/.well-known/openid-configuration"
      oidc_client_id            = "example-client"
      security_compartment_ocid = "ocid1.compartment.oc1..securityexample"
      database_secret_ocid      = "ocid1.vaultsecret.oc1..databaseexample"
      database_secret_version   = 1
      oidc_client_secret_ocid   = "ocid1.vaultsecret.oc1..identityexample"
      session_secret_ocid       = "ocid1.vaultsecret.oc1..sessionexample"
    }
  }
  expect_failures = [var.production]
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
