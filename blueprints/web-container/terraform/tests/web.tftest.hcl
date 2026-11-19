# Provider mocks only. These tests perform no cloud reads or writes.
mock_provider "oci" {}
mock_provider "oci" {
  alias = "home"
}

override_data {
  target = data.oci_core_subnet.public
  values = {
    vcn_id                     = "ocid1.vcn.oc1..example"
    cidr_block                 = "10.20.1.0/24"
    prohibit_public_ip_on_vnic = false
  }
}

override_data {
  target = data.oci_core_subnet.private
  values = {
    vcn_id                     = "ocid1.vcn.oc1..example"
    cidr_block                 = "10.20.2.0/24"
    prohibit_public_ip_on_vnic = true
  }
}

variables {
  tenancy_ocid          = "ocid1.tenancy.oc1..example"
  compartment_ocid      = "ocid1.compartment.oc1..example"
  region                = "us-ashburn-1"
  home_region           = "us-ashburn-1"
  availability_domain   = "EXAMPLE:US-ASHBURN-AD-1"
  allowed_ingress_cidrs = ["203.0.113.10/32"]
  certificate_ocid      = "ocid1.certificate.oc1..example"
  public_origin         = "https://rehearsal.example.test"
  app_image             = "iad.ocir.io/example/founder-app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  network = {
    vcn_ocid            = "ocid1.vcn.oc1..example"
    public_subnet_ocid  = "ocid1.subnet.oc1..publicexample"
    private_subnet_ocid = "ocid1.subnet.oc1..privateexample"
    app_private_ip      = "10.20.2.10"
  }
  registry = {
    compartment_ocid = "ocid1.compartment.oc1..example"
    repository_name  = "founder-app"
  }
  application_contract = {
    evidence_sha256 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    background_work = "absent"
  }
}

run "reuses_network_and_iam_with_https_only" {
  command = plan
  assert {
    condition     = length(oci_identity_dynamic_group.runtime) == 0 && length(oci_identity_policy.registry) == 0 && length(oci_identity_policy.secrets) == 0
    error_message = "Default plans must not create IAM."
  }
  assert {
    condition     = oci_load_balancer_listener.https.port == 443 && toset(oci_load_balancer_listener.https.ssl_configuration[0].protocols) == toset(["TLSv1.2", "TLSv1.3"])
    error_message = "HTTPS must be the sole listener with the configured modern TLS versions."
  }
  assert {
    condition     = !oci_container_instances_container_instance.app.vnics[0].is_public_ip_assigned && oci_container_instances_container_instance.app.vnics[0].subnet_id == var.network.private_subnet_ocid
    error_message = "The app must remain private in the selected existing subnet."
  }
  assert {
    condition     = oci_core_network_security_group_security_rule.lb_in_https["203.0.113.10/32"].tcp_options[0].destination_port_range[0].min == 443 && oci_core_network_security_group_security_rule.app_in_lb.source_type == "NETWORK_SECURITY_GROUP"
    error_message = "Only selected HTTPS clients and the load-balancer app path may be granted ingress."
  }
  assert {
    condition     = local.app_environment.PORT == "8080" && !contains(keys(local.app_environment), "DATABASE_URL")
    error_message = "The default app environment must contain only nonsecret platform settings."
  }
}

run "custom_port_health_and_disabled_workers" {
  command = plan
  variables {
    app_port    = 3000
    health_path = "/api/ready"
    application_contract = {
      evidence_sha256 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      background_work = "disabled"
      background_control_environment = {
        RUN_WORKERS = "false"
      }
    }
    public_environment = {
      NODE_ENV = "production"
    }
    dependency_egress = {
      postgres = { destination_cidr = "198.51.100.20/32", port = 5432 }
    }
  }
  assert {
    condition     = local.app_environment.PORT == "3000" && local.app_environment.RUN_WORKERS == "false" && local.app_environment.NODE_ENV == "production"
    error_message = "Explicit app settings must be preserved."
  }
  assert {
    condition     = oci_load_balancer_backend.app.port == 3000 && oci_load_balancer_backend_set.app.health_checker[0].url_path == "/api/ready" && oci_container_instances_container_instance.app.containers[0].health_checks[0].port == 3000
    error_message = "Container, backend and health checks must share the selected port/path."
  }
  assert {
    condition     = oci_core_network_security_group_security_rule.app_out_dependencies["postgres"].destination == "198.51.100.20/32" && oci_core_network_security_group_security_rule.app_out_dependencies["postgres"].tcp_options[0].destination_port_range[0].max == 5432
    error_message = "External dependencies must use only selected destinations and ports."
  }
}

run "explicit_scoped_runtime_iam" {
  command = plan
  variables {
    manage_runtime_iam = true
    secret_references = {
      DATABASE_SECRET_OCID = {
        secret_ocid      = "ocid1.vaultsecret.oc1..databaseexample"
        compartment_ocid = "ocid1.compartment.oc1..securityexample"
      }
    }
    application_contract = {
      evidence_sha256              = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      background_work              = "absent"
      vault_references_implemented = true
    }
  }
  assert {
    condition     = length(oci_identity_policy.secrets) == 1 && strcontains(oci_identity_policy.secrets["DATABASE_SECRET_OCID"].statements[0], "where target.secret.id = 'ocid1.vaultsecret.oc1..databaseexample'") && strcontains(oci_identity_policy.registry[0].statements[0], "where target.repo.name = 'founder-app'")
    error_message = "Runtime IAM must be scoped to each selected secret and repository."
  }
  assert {
    condition     = local.app_environment.DATABASE_SECRET_OCID == "ocid1.vaultsecret.oc1..databaseexample" && !contains(keys(local.app_environment), "DATABASE_URL")
    error_message = "Only a secret identifier may be injected."
  }
}

run "reject_unreviewed_application" {
  command = plan
  variables {
    application_contract = { evidence_sha256 = "", background_work = "unverified" }
  }
  expect_failures = [oci_container_instances_container_instance.app]
}

run "reject_fake_worker_disable" {
  command = plan
  variables {
    application_contract = { evidence_sha256 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", background_work = "disabled" }
  }
  expect_failures = [oci_container_instances_container_instance.app]
}

run "reject_worker_activation" {
  command = plan
  variables {
    application_contract = {
      evidence_sha256                = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      background_work                = "disabled"
      background_control_environment = { RUN_WORKERS = "true" }
    }
  }
  expect_failures = [var.application_contract]
}

run "reject_secret_reference_without_adapter" {
  command = plan
  variables {
    secret_references = {
      DATABASE_SECRET_OCID = { secret_ocid = "ocid1.vaultsecret.oc1..databaseexample", compartment_ocid = "ocid1.compartment.oc1..securityexample" }
    }
  }
  expect_failures = [oci_container_instances_container_instance.app]
}

run "reject_plaintext_secret_setting" {
  command = plan
  variables {
    public_environment = { DATABASE_URL = "postgres://placeholder@db.example.test/app" }
  }
  expect_failures = [var.public_environment]
}

run "reject_reserved_setting" {
  command = plan
  variables {
    public_environment = { PORT = "9000" }
  }
  expect_failures = [var.public_environment]
}

run "reject_mutable_image" {
  command = plan
  variables {
    app_image = "iad.ocir.io/example/founder-app:latest"
  }
  expect_failures = [var.app_image]
}

run "reject_wrong_repository" {
  command = plan
  variables {
    registry = { compartment_ocid = "ocid1.compartment.oc1..example", repository_name = "other-app" }
  }
  expect_failures = [oci_container_instances_container_instance.app]
}

run "reject_wrong_vcn" {
  command = plan
  override_data {
    target = data.oci_core_subnet.private
    values = { vcn_id = "ocid1.vcn.oc1..otherexample", cidr_block = "10.20.2.0/24", prohibit_public_ip_on_vnic = true }
  }
  expect_failures = [oci_container_instances_container_instance.app]
}

run "reject_public_app_subnet" {
  command = plan
  override_data {
    target = data.oci_core_subnet.private
    values = { vcn_id = "ocid1.vcn.oc1..example", cidr_block = "10.20.2.0/24", prohibit_public_ip_on_vnic = false }
  }
  expect_failures = [oci_container_instances_container_instance.app]
}

run "reject_wrong_private_ip" {
  command = plan
  variables {
    network = {
      vcn_ocid            = "ocid1.vcn.oc1..example"
      public_subnet_ocid  = "ocid1.subnet.oc1..publicexample"
      private_subnet_ocid = "ocid1.subnet.oc1..privateexample"
      app_private_ip      = "10.99.2.10"
    }
  }
  expect_failures = [oci_container_instances_container_instance.app]
}

run "reject_non_https_origin" {
  command = plan
  variables {
    public_origin = "http://rehearsal.example.test"
  }
  expect_failures = [var.public_origin]
}

run "reject_similar_nested_repository" {
  command = plan
  variables {
    app_image = "iad.ocir.io/example/other/founder-app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  expect_failures = [oci_container_instances_container_instance.app]
}
run "api_key_is_not_public_environment" {
  command = plan
  variables {
    public_environment = { API_KEY = "synthetic-private-value" }
  }
  expect_failures = [var.public_environment]
}
