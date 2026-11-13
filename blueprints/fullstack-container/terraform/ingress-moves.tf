# Adding an optional ingress must not replace an existing load-balancer stack.
moved {
  from = oci_core_subnet.public
  to   = oci_core_subnet.public[0]
}
moved {
  from = oci_core_network_security_group.lb
  to   = oci_core_network_security_group.lb[0]
}
moved {
  from = oci_core_network_security_group_security_rule.lb_out_app
  to   = oci_core_network_security_group_security_rule.lb_out_app[0]
}
moved {
  from = oci_core_network_security_group_security_rule.app_in_lb
  to   = oci_core_network_security_group_security_rule.app_in_lb[0]
}
moved {
  from = oci_load_balancer_load_balancer.web
  to   = oci_load_balancer_load_balancer.web[0]
}
moved {
  from = oci_load_balancer_backend_set.app
  to   = oci_load_balancer_backend_set.app[0]
}
moved {
  from = oci_load_balancer_backend.app
  to   = oci_load_balancer_backend.app[0]
}
moved {
  from = oci_monitoring_alarm.unhealthy_backend
  to   = oci_monitoring_alarm.unhealthy_backend[0]
}
moved {
  from = oci_ons_notification_topic.alerts
  to   = oci_ons_notification_topic.alerts[0]
}
