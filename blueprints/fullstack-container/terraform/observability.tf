resource "oci_ons_notification_topic" "alerts" {
  compartment_id = var.compartment_ocid
  name           = "${var.name}-alerts"
}

resource "oci_ons_subscription" "email" {
  count          = var.alert_email == "" ? 0 : 1
  compartment_id = var.compartment_ocid
  topic_id       = oci_ons_notification_topic.alerts.id
  protocol       = "EMAIL"
  endpoint       = var.alert_email
}

resource "oci_monitoring_alarm" "unhealthy_backend" {
  compartment_id        = var.compartment_ocid
  metric_compartment_id = var.compartment_ocid
  display_name          = "${var.name} app unhealthy"
  namespace             = "oci_lbaas"
  query                 = "UnHealthyBackendServers[1m]{resourceId = \"${oci_load_balancer_load_balancer.web.id}\"}.max() > 0"
  severity              = "CRITICAL"
  is_enabled            = true
  pending_duration      = "PT5M"
  destinations          = [oci_ons_notification_topic.alerts.id]
  body                  = "The load balancer reports an unhealthy ${var.name} backend for five minutes."
}
