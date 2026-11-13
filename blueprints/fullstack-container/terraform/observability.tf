resource "oci_ons_notification_topic" "alerts" {
  count          = local.load_balancer_enabled ? 1 : 0
  compartment_id = var.compartment_ocid
  name           = "${var.name}-alerts"
}

resource "oci_ons_subscription" "email" {
  count          = local.load_balancer_enabled && var.alert_email != "" ? 1 : 0
  compartment_id = var.compartment_ocid
  topic_id       = oci_ons_notification_topic.alerts[0].id
  protocol       = "EMAIL"
  endpoint       = var.alert_email
}

resource "oci_monitoring_alarm" "unhealthy_backend" {
  count                 = local.load_balancer_enabled ? 1 : 0
  compartment_id        = var.compartment_ocid
  metric_compartment_id = var.compartment_ocid
  display_name          = "${var.name} app unhealthy"
  namespace             = "oci_lbaas"
  query                 = "UnHealthyBackendServers[1m]{resourceId = \"${oci_load_balancer_load_balancer.web[0].id}\"}.max() > 0"
  severity              = "CRITICAL"
  is_enabled            = true
  pending_duration      = "PT5M"
  destinations          = [oci_ons_notification_topic.alerts[0].id]
  body                  = "The load balancer reports an unhealthy ${var.name} backend for five minutes."
}
