# No monitoring resources, recurring probes or email invitations until opted in.
variable "monitoring" {
  description = "Private opt-in. Confirm both destinations and reviewed probe locations before approving the plan. Email addresses enter private Terraform state."
  type = object({
    primary_email  = string
    backup_email   = string
    vantage_points = set(string)
    journey        = string
  })
  default = null
  validation {
    condition = var.monitoring == null ? true : (
      alltrue([for address in [var.monitoring.primary_email, var.monitoring.backup_email] :
      can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", address)) && length(address) <= 254]) &&
      lower(var.monitoring.primary_email) != lower(var.monitoring.backup_email) &&
      length(var.monitoring.vantage_points) >= 1 && length(var.monitoring.vantage_points) <= 3 &&
      alltrue([for name in var.monitoring.vantage_points : can(regex("^[a-z][a-z0-9-]{1,31}$", name))]) &&
      can(regex("^[a-z][a-z0-9-]{0,39}$", var.monitoring.journey))
    )
    error_message = "Select two distinct email routes, a short journey identifier, and one to three reviewed public vantage points."
  }
}

resource "oci_ons_notification_topic" "alerts" {
  count          = var.monitoring == null ? 0 : 1
  compartment_id = var.compartment_ocid
  name           = "${var.name}-alerts"
}

resource "oci_ons_subscription" "responders" {
  for_each       = var.monitoring == null ? toset([]) : toset(["primary", "backup"])
  compartment_id = var.compartment_ocid
  topic_id       = oci_ons_notification_topic.alerts[0].id
  protocol       = "EMAIL"
  endpoint       = sensitive(each.key == "primary" ? var.monitoring.primary_email : var.monitoring.backup_email)
}

resource "oci_health_checks_http_monitor" "external" {
  count               = var.monitoring == null ? 0 : 1
  compartment_id      = var.compartment_ocid
  display_name        = "${var.name}-external-https"
  protocol            = "HTTPS"
  port                = 443
  method              = "GET"
  targets             = [trimsuffix(trimprefix(var.public_origin, "https://"), ":443")]
  path                = var.health_path
  timeout_in_seconds  = 10
  interval_in_seconds = 60
  vantage_point_names = sort(tolist(var.monitoring.vantage_points))
  is_enabled          = true
}

locals {
  sre_alerts = var.monitoring == null ? {} : {
    backend = {
      namespace = "oci_lbaas"
      query     = "UnHealthyBackendServers[1m]{resourceId = \"${oci_load_balancer_load_balancer.web.id}\"}.max() > 0"
      delay     = "PT5M"
      body      = "Backend unavailable. Check external HTTPS and the current deployment before changing the service."
    }
    probe = {
      namespace = "oci_healthchecks"
      query     = "HTTP.isHealthy[1m]{resourceId = \"${oci_health_checks_http_monitor.external[0].id}\"}.groupBy(vantagePoint).max() == 0"
      delay     = "PT3M"
      body      = "External probes are failing. Check DNS, TLS and ingress from the reviewed vantage point."
    }
    telemetry = {
      namespace = "founder_app"
      query     = "Heartbeat[5m]{resourceId = \"${oci_container_instances_container_instance.app.id}\",journey = \"${var.monitoring.journey}\"}.groupBy(resourceId, journey).absent()"
      delay     = "PT5M"
      body      = "Application telemetry is missing. Verify the exporter and user journey; missing metrics do not indicate success."
    }
  }
}

resource "oci_monitoring_alarm" "sre" {
  for_each              = local.sre_alerts
  compartment_id        = var.compartment_ocid
  metric_compartment_id = var.compartment_ocid
  display_name          = "${var.name}-${each.key}"
  namespace             = each.value.namespace
  query                 = each.value.query
  pending_duration      = each.value.delay
  severity              = each.key == "telemetry" ? "WARNING" : "CRITICAL"
  body                  = each.value.body
  destinations          = [oci_ons_notification_topic.alerts[0].id]
  is_enabled            = true
}
