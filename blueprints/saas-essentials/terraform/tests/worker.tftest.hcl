mock_provider "oci" {}
mock_provider "oci" { alias = "home" }
override_data {
  target = data.oci_core_subnet.private
  values = { vcn_id = "ocid1.vcn.oc1..example", prohibit_public_ip_on_vnic = true }
}
variables {
  region               = "us-ashburn-1"
  home_region          = "us-ashburn-1"
  tenancy_ocid         = "ocid1.tenancy.oc1..example"
  config_file_profile  = "DEFAULT"
  auth                 = "SecurityToken"
  name                 = "rehearsal"
  compartment_ocid     = "ocid1.compartment.oc1..worker"
  web_compartment_ocid = "ocid1.compartment.oc1..web"
  availability_domain  = "EXAMPLE:US-ASHBURN-AD-1"
  app_image            = "iad.ocir.io/example/worker@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  network              = { vcn_ocid = "ocid1.vcn.oc1..example", private_subnet_ocid = "ocid1.subnet.oc1..example", app_private_ip = "10.20.3.10" }
  registry             = { compartment_ocid = "ocid1.compartment.oc1..registry", repository_name = "worker" }
  public_environment   = { DATABASE_HOST = "db.example.invalid", DATABASE_NAME = "requests", DATABASE_USER = "worker", DATABASE_CA_CERT = "synthetic-public-ca" }
  secret_references    = { DATABASE_PASSWORD_SECRET_OCID = { secret_ocid = "ocid1.vaultsecret.oc1..worker", compartment_ocid = "ocid1.compartment.oc1..security" } }
  egress               = { database = { cidr = "10.20.4.10/32", protocol = "6", port = 5432 } }
}
run "private_worker_and_bounded_queue" {
  command = plan
  assert {
    condition     = !oci_container_instances_container_instance.worker.vnics[0].is_public_ip_assigned && oci_container_instances_container_instance.worker.compartment_id != var.web_compartment_ocid
    error_message = "Worker must be private with distinct identity membership."
  }
  assert {
    condition     = length(oci_identity_policy.queue) == 0 && length(oci_identity_dynamic_group.runtime) == 0
    error_message = "IAM creation must remain explicit."
  }
  assert {
    condition     = oci_queue_queue.jobs.dead_letter_queue_delivery_count == 10 && oci_queue_queue.jobs.retention_in_seconds == 604800
    error_message = "Queue must retain a bounded DLQ and declared retention."
  }
}
run "shared_web_identity_refused" {
  command = plan
  variables { web_compartment_ocid = "ocid1.compartment.oc1..worker" }
  expect_failures = [oci_container_instances_container_instance.worker]
}
run "mutable_image_refused" {
  command = plan
  variables { app_image = "iad.ocir.io/example/worker:latest" }
  expect_failures = [var.app_image]
}
run "plaintext_database_secret_refused" {
  command = plan
  variables { public_environment = { DATABASE_PASSWORD = "synthetic-forbidden" } }
  expect_failures = [var.public_environment]
}
run "iam_is_worker_scoped" {
  command = apply
  variables { manage_runtime_iam = true }
  assert {
    condition     = strcontains(oci_identity_dynamic_group.runtime[0].name, "-worker-") && oci_identity_dynamic_group.runtime[0].name != "${var.name}-containers" && strcontains(oci_identity_policy.registry[0].name, "-worker-")
    error_message = "Worker IAM names must be distinct from web and other projects' environment names."
  }
  assert {
    condition     = strcontains(oci_identity_dynamic_group.runtime[0].matching_rule, var.compartment_ocid) && !strcontains(oci_identity_dynamic_group.runtime[0].matching_rule, var.web_compartment_ocid)
    error_message = "The web application cannot join the worker group."
  }
  assert {
    condition     = alltrue([for statement in oci_identity_policy.queue[0].statements : strcontains(statement, "where target.queue.id = '") && !strcontains(statement, "manage")])
    error_message = "Queue grants must be selected push/pull permissions, without administration."
  }
}
