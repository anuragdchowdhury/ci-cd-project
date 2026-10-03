locals { suffix = substr(sha256(var.subscription_id), 0, 8) }
resource "azurerm_private_link_service" "ingress" {
  name                                        = "pls-nk-dev-ingress"
  location                                    = var.location
  resource_group_name                         = var.resource_group
  load_balancer_frontend_ip_configuration_ids = [var.load_balancer_frontend_id]
  # Front Door uses a Microsoft-managed subscription. Connection approval is
  # explicit; visibility does not grant access and there is no auto-approval.
  visibility_subscription_ids = ["*"]
  nat_ip_configuration {
    name                       = "primary"
    primary                    = true
    subnet_id                  = var.ingress_subnet_id
    private_ip_address         = "10.20.19.11"
    private_ip_address_version = "IPv4"
  }
}
resource "azurerm_cdn_frontdoor_profile" "dev" {
  name                     = "afd-nk-dev"
  resource_group_name      = var.resource_group
  sku_name                 = "Premium_AzureFrontDoor"
  response_timeout_seconds = 30
}
resource "azurerm_cdn_frontdoor_endpoint" "dev" {
  name                     = "nk-dev-${local.suffix}"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.dev.id
}
resource "azurerm_cdn_frontdoor_origin_group" "dev" {
  name                     = "private-aks"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.dev.id
  health_probe {
    interval_in_seconds = 60
    path                = "/healthz"
    protocol            = "Https"
    request_type        = "GET"
  }
  load_balancing {
    sample_size                 = 4
    successful_samples_required = 3
  }
}
resource "azurerm_cdn_frontdoor_origin" "dev" {
  name                           = "private-ingress"
  cdn_frontdoor_origin_group_id  = azurerm_cdn_frontdoor_origin_group.dev.id
  enabled                        = true
  host_name                      = "origin.${var.dev_dns_zone}"
  origin_host_header             = "origin.${var.dev_dns_zone}"
  certificate_name_check_enabled = true
  https_port                     = 443
  http_port                      = 80
  priority                       = 1
  weight                         = 1000
  private_link {
    request_message        = "NoteKeeper Dev Front Door Premium to Terraform-managed ingress PLS"
    location               = var.location
    private_link_target_id = azurerm_private_link_service.ingress.id
  }
  depends_on = [azurerm_private_link_service.ingress]
}
resource "azurerm_cdn_frontdoor_custom_domain" "dev" {
  name                     = "dev-domain"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.dev.id
  host_name                = var.dev_dns_zone
  tls {
    certificate_type = "ManagedCertificate"
    minimum_version  = "TLS12"
  }
}
resource "azurerm_dns_txt_record" "frontdoor_validation" {
  name                = "_dnsauth"
  zone_name           = var.dev_dns_zone
  resource_group_name = var.resource_group
  ttl                 = 300
  record { value = azurerm_cdn_frontdoor_custom_domain.dev.validation_token }
}
# Apex of the delegated Dev zone uses Azure DNS alias, rather than an illegal
# CNAME at a zone apex.
resource "azurerm_dns_a_record" "frontdoor" {
  name                = "@"
  zone_name           = var.dev_dns_zone
  resource_group_name = var.resource_group
  ttl                 = 300
  target_resource_id  = azurerm_cdn_frontdoor_endpoint.dev.id
}
resource "azurerm_cdn_frontdoor_route" "dev" {
  name                            = "website"
  cdn_frontdoor_endpoint_id       = azurerm_cdn_frontdoor_endpoint.dev.id
  cdn_frontdoor_origin_group_id   = azurerm_cdn_frontdoor_origin_group.dev.id
  cdn_frontdoor_origin_ids        = [azurerm_cdn_frontdoor_origin.dev.id]
  cdn_frontdoor_custom_domain_ids = [azurerm_cdn_frontdoor_custom_domain.dev.id]
  enabled                         = true
  forwarding_protocol             = "HttpsOnly"
  https_redirect_enabled          = true
  patterns_to_match               = ["/*"]
  supported_protocols             = ["Http", "Https"]
  link_to_default_domain          = true
  # No API caching; ingress splits /api/ from /.
}
resource "azurerm_cdn_frontdoor_firewall_policy" "dev" {
  name                = "nknoteKeeperDev"
  resource_group_name = var.resource_group
  sku_name            = azurerm_cdn_frontdoor_profile.dev.sku_name
  enabled             = true
  mode                = "Prevention"
  custom_rule {
    name     = "OperatorOnly"
    enabled  = true
    priority = 1
    type     = "MatchRule"
    action   = "Block"
    match_condition {
      match_variable     = "RemoteAddr"
      operator           = "IPMatch"
      negation_condition = true
      match_values       = ["${var.operator_ipv4}/32"]
    }
  }
  managed_rule {
    type    = "Microsoft_DefaultRuleSet"
    version = "2.1"
    action  = "Block"
  }
}
resource "azurerm_cdn_frontdoor_security_policy" "dev" {
  name                     = "waf"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.dev.id
  security_policies {
    firewall {
      cdn_frontdoor_firewall_policy_id = azurerm_cdn_frontdoor_firewall_policy.dev.id
      association {
        domain { cdn_frontdoor_domain_id = azurerm_cdn_frontdoor_endpoint.dev.id }
        domain { cdn_frontdoor_domain_id = azurerm_cdn_frontdoor_custom_domain.dev.id }
        patterns_to_match = ["/*"]
      }
    }
  }
}
resource "azurerm_monitor_diagnostic_setting" "frontdoor" {
  name                           = "frontdoor-logs-once"
  target_resource_id             = azurerm_cdn_frontdoor_profile.dev.id
  log_analytics_workspace_id     = var.law_id
  log_analytics_destination_type = "Dedicated"
  enabled_log { category = "FrontDoorAccessLog" }
  enabled_log { category = "FrontDoorHealthProbeLog" }
  enabled_log { category = "FrontDoorWebApplicationFirewallLog" }
  # No allLogs category group and no metric copy to Log Analytics.
}
resource "azurerm_monitor_metric_alert" "origin_health" {
  name                     = "nk-dev-origin-unhealthy"
  resource_group_name      = var.resource_group
  scopes                   = [azurerm_cdn_frontdoor_profile.dev.id]
  target_resource_type     = "Microsoft.Cdn/profiles"
  target_resource_location = "global"
  severity                 = 2
  frequency                = "PT1M"
  window_size              = "PT5M"
  criteria {
    metric_namespace = "Microsoft.Cdn/profiles"
    metric_name      = "OriginHealthPercentage"
    aggregation      = "Average"
    operator         = "LessThan"
    threshold        = 80
  }
  action { action_group_id = var.action_group_id }
}
output "edge" {
  value = {
    endpoint                = azurerm_cdn_frontdoor_endpoint.dev.host_name
    url                     = "https://${var.dev_dns_zone}"
    origin_host             = "origin.${var.dev_dns_zone}"
    private_link_service_id = azurerm_private_link_service.ingress.id
    frontdoor_id            = azurerm_cdn_frontdoor_profile.dev.resource_guid
  }
}
