locals {
  lab_count         = var.lab_enabled ? 1 : 0
  container_streams = ["Microsoft-ContainerLogV2", "Microsoft-KubeEvents"]
  log_transform     = var.logs_drill_mode ? "source | where PodNamespace in ('notekeeper-dev', 'lab-scenarios')" : "source | where PodNamespace in ('notekeeper-dev', 'lab-scenarios') | extend parsed = parse_json(tostring(LogMessage)) | extend severity = toupper(iif(isnotempty(tostring(parsed.level)), tostring(parsed.level), LogLevel)) | where severity in ('ERROR', 'CRITICAL', 'FATAL') | project-away parsed, severity"
  alert_rules = {
    ApiErrors     = { expression = "sum(rate(http_server_requests_seconds_count{job=\"notekeeper-api\",status=~\"5..\"}[5m])) / clamp_min(sum(rate(http_server_requests_seconds_count{job=\"notekeeper-api\"}[5m])),0.001) > 0.05", duration = "PT2M" }
    ApiLatency    = { expression = "histogram_quantile(0.95,sum by(le)(rate(http_server_requests_seconds_bucket{job=\"notekeeper-api\"}[5m]))) > 1", duration = "PT2M" }
    ApiNotReady   = { expression = "kube_pod_status_ready{namespace=\"notekeeper-dev\",condition=\"true\",pod=~\"notekeeper-api-.*\"} == 0", duration = "PT2M" }
    ApiDown       = { expression = "up{job=\"notekeeper-api\"} == 0 or absent(up{job=\"notekeeper-api\"})", duration = "PT2M" }
    PodRestarts   = { expression = "sum(increase(kube_pod_container_status_restarts_total{namespace=~\"notekeeper-dev|lab-scenarios\"}[10m])) > 2", duration = "PT1M" }
    PodPending    = { expression = "sum(kube_pod_status_phase{namespace=\"lab-scenarios\",phase=\"Pending\"}) > 0", duration = "PT2M" }
    NodeNotReady  = { expression = "sum(kube_node_status_condition{condition=\"Ready\",status=\"true\"} == 0) > 0", duration = "PT2M" }
    CpuSaturation = { expression = "sum(rate(container_cpu_usage_seconds_total{namespace=\"notekeeper-dev\",container=\"backend\"}[5m])) > 0.8", duration = "PT2M" }
    DbPoolWait    = { expression = "sum(hikaricp_connections_pending{job=\"notekeeper-api\"}) > 0", duration = "PT2M" }
  }
}
resource "azurerm_log_analytics_workspace" "lab" {
  count               = local.lab_count
  name                = "law-${var.name_prefix}-dev-${local.suffix}"
  resource_group_name = azurerm_resource_group.platform.name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.5
  tags                = local.tags
}
resource "azurerm_monitor_workspace" "lab" {
  count               = local.lab_count
  name                = "amw-${var.name_prefix}-dev-${local.suffix}"
  resource_group_name = azurerm_resource_group.platform.name
  location            = var.location
  tags                = local.tags
}
resource "azurerm_application_insights" "lab" {
  for_each            = var.lab_enabled ? toset(["backend", "browser"]) : toset([])
  name                = "appi-${var.name_prefix}-dev-${each.value}"
  resource_group_name = azurerm_resource_group.platform.name
  location            = var.location
  workspace_id        = azurerm_log_analytics_workspace.lab[0].id
  application_type    = "web"
  retention_in_days   = 30
  sampling_percentage = 100
  # Browser cannot use a confidential identity; pinned Java agent uses IMDS,
  # not direct workload identity. See the explicit lab exception in the runbook.
  local_authentication_enabled = true
  tags                         = local.tags
}
resource "azurerm_monitor_data_collection_endpoint" "prometheus" {
  count               = local.lab_count
  name                = "dce-${var.name_prefix}-dev-prometheus"
  resource_group_name = azurerm_resource_group.platform.name
  location            = var.location
  kind                = "Linux"
}
resource "azurerm_monitor_data_collection_rule" "prometheus" {
  count                       = local.lab_count
  name                        = "dcr-${var.name_prefix}-dev-prometheus"
  resource_group_name         = azurerm_resource_group.platform.name
  location                    = var.location
  kind                        = "Linux"
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.prometheus[0].id
  destinations {
    monitor_account {
      name               = "prometheus"
      monitor_account_id = azurerm_monitor_workspace.lab[0].id
    }
  }
  data_sources {
    prometheus_forwarder {
      name    = "prometheus"
      streams = ["Microsoft-PrometheusMetrics"]
    }
  }
  data_flow {
    streams      = ["Microsoft-PrometheusMetrics"]
    destinations = ["prometheus"]
  }
}
resource "azurerm_monitor_data_collection_rule_association" "prometheus" {
  count                   = local.lab_count
  name                    = "notekeeper-prometheus"
  target_resource_id      = azurerm_kubernetes_cluster.platform.id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.prometheus[0].id
}
resource "azurerm_monitor_data_collection_rule" "containers" {
  count               = local.lab_count
  name                = "dcr-${var.name_prefix}-dev-containers"
  resource_group_name = azurerm_resource_group.platform.name
  location            = var.location
  kind                = "Linux"
  destinations {
    log_analytics {
      name                  = "logs"
      workspace_resource_id = azurerm_log_analytics_workspace.lab[0].id
    }
  }
  data_sources {
    extension {
      name           = "container-insights"
      extension_name = "ContainerInsights"
      streams        = local.container_streams
      extension_json = jsonencode({ dataCollectionSettings = {
        interval = "1m", namespaceFilteringMode = "Include", namespaces = ["notekeeper-dev", "lab-scenarios"], enableContainerLogV2 = true
      } })
    }
  }
  data_flow {
    streams       = ["Microsoft-ContainerLogV2"]
    destinations  = ["logs"]
    transform_kql = local.log_transform
  }
  data_flow {
    streams      = ["Microsoft-KubeEvents"]
    destinations = ["logs"]
  }
}
resource "azurerm_monitor_data_collection_rule_association" "containers" {
  count                   = local.lab_count
  name                    = "notekeeper-containers"
  target_resource_id      = azurerm_kubernetes_cluster.platform.id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.containers[0].id
}
resource "azurerm_dashboard_grafana" "lab" {
  count                         = local.lab_count
  name                          = "grafana-${var.name_prefix}-dev-${local.suffix}"
  resource_group_name           = azurerm_resource_group.platform.name
  location                      = var.location
  grafana_major_version         = 13
  sku                           = "Standard"
  sku_size                      = "X1"
  api_key_enabled               = false
  public_network_access_enabled = true
  zone_redundancy_enabled       = false
  identity { type = "SystemAssigned" }
  azure_monitor_workspace_integrations { resource_id = azurerm_monitor_workspace.lab[0].id }
  tags = local.tags
}
resource "azurerm_role_assignment" "grafana_prometheus" {
  count                = local.lab_count
  scope                = azurerm_monitor_workspace.lab[0].id
  role_definition_name = "Monitoring Data Reader"
  principal_id         = azurerm_dashboard_grafana.lab[0].identity[0].principal_id
  principal_type       = "ServicePrincipal"
}
resource "azurerm_role_assignment" "grafana_logs" {
  count                = local.lab_count
  scope                = azurerm_log_analytics_workspace.lab[0].id
  role_definition_name = "Log Analytics Reader"
  principal_id         = azurerm_dashboard_grafana.lab[0].identity[0].principal_id
  principal_type       = "ServicePrincipal"
}
resource "azurerm_role_assignment" "grafana_operator" {
  count                = local.lab_count
  scope                = azurerm_dashboard_grafana.lab[0].id
  role_definition_name = "Grafana Admin"
  principal_id         = var.operator_object_id
  principal_type       = "User"
}
resource "azurerm_monitor_action_group" "lab" {
  count               = local.lab_count
  name                = "ag-${var.name_prefix}-dev-lab"
  resource_group_name = azurerm_resource_group.platform.name
  short_name          = "nk-dev-lab"
  email_receiver {
    name                    = "operator"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
}
resource "azurerm_monitor_alert_prometheus_rule_group" "lab" {
  count               = local.lab_count
  name                = "alerts-${var.name_prefix}-dev"
  resource_group_name = azurerm_resource_group.platform.name
  location            = var.location
  scopes              = [azurerm_monitor_workspace.lab[0].id, azurerm_kubernetes_cluster.platform.id]
  cluster_name        = azurerm_kubernetes_cluster.platform.name
  interval            = "PT1M"
  rule_group_enabled  = true
  dynamic "rule" {
    for_each = local.alert_rules
    content {
      alert       = rule.key
      enabled     = true
      expression  = rule.value.expression
      for         = rule.value.duration
      severity    = 2
      labels      = { environment = "dev", project = "notekeeper" }
      annotations = { summary = rule.key, runbook = "docs/07-scenarios.md" }
      action { action_group_id = azurerm_monitor_action_group.lab[0].id }
      alert_resolution {
        auto_resolved   = true
        time_to_resolve = "PT5M"
      }
    }
  }
}
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "errors" {
  count                 = local.lab_count
  name                  = "alert-${var.name_prefix}-dev-container-errors"
  resource_group_name   = azurerm_resource_group.platform.name
  location              = var.location
  scopes                = [azurerm_log_analytics_workspace.lab[0].id]
  severity              = 2
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  skip_query_validation = true
  criteria {
    query                   = "ContainerLogV2 | where PodNamespace == 'notekeeper-dev' | extend parsed=parse_json(tostring(LogMessage)) | where toupper(tostring(coalesce(tostring(parsed.level),LogLevel))) in ('ERROR','CRITICAL','FATAL')"
    time_aggregation_method = "Count"
    operator                = "GreaterThanOrEqual"
    threshold               = 5
    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }
  action { action_groups = [azurerm_monitor_action_group.lab[0].id] }
}
# Website DNS zone: registrar delegation remains an operator step.
resource "azurerm_dns_zone" "dev" {
  count               = local.lab_count
  name                = var.dev_dns_zone
  resource_group_name = azurerm_resource_group.platform.name
  tags                = local.tags
}
resource "azurerm_dns_a_record" "origin" {
  count               = local.lab_count
  name                = "origin"
  zone_name           = azurerm_dns_zone.dev[0].name
  resource_group_name = azurerm_resource_group.platform.name
  ttl                 = 300
  records             = ["10.20.19.10"]
}
resource "azurerm_user_assigned_identity" "cert_manager" {
  count               = local.lab_count
  name                = "id-${var.name_prefix}-dev-cert-manager"
  resource_group_name = azurerm_resource_group.platform.name
  location            = var.location
}
resource "azurerm_federated_identity_credential" "cert_manager" {
  count                     = local.lab_count
  name                      = "aks-cert-manager"
  user_assigned_identity_id = azurerm_user_assigned_identity.cert_manager[0].id
  issuer                    = azurerm_kubernetes_cluster.platform.oidc_issuer_url
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "system:serviceaccount:cert-manager:cert-manager"
}
resource "azurerm_role_assignment" "cert_dns" {
  count                = local.lab_count
  scope                = azurerm_dns_zone.dev[0].id
  role_definition_name = "DNS Zone Contributor"
  principal_id         = azurerm_user_assigned_identity.cert_manager[0].principal_id
  principal_type       = "ServicePrincipal"
}
output "observability" {
  value = var.lab_enabled ? {
    resource_group            = azurerm_resource_group.platform.name
    law_id                    = azurerm_log_analytics_workspace.lab[0].id
    law_customer_id           = azurerm_log_analytics_workspace.lab[0].workspace_id
    prometheus_id             = azurerm_monitor_workspace.lab[0].id
    prometheus_query_endpoint = azurerm_monitor_workspace.lab[0].query_endpoint
    grafana_name              = azurerm_dashboard_grafana.lab[0].name
    grafana_endpoint          = azurerm_dashboard_grafana.lab[0].endpoint
    backend_connection_string = nonsensitive(azurerm_application_insights.lab["backend"].connection_string)
    browser_connection_string = nonsensitive(azurerm_application_insights.lab["browser"].connection_string)
    dev_dns_zone              = azurerm_dns_zone.dev[0].name
    nameservers               = azurerm_dns_zone.dev[0].name_servers
    cert_manager_client_id    = azurerm_user_assigned_identity.cert_manager[0].client_id
    subscription_id           = var.subscription_id
    tenant_id                 = var.tenant_id
    acme_email                = var.alert_email
    action_group_id           = azurerm_monitor_action_group.lab[0].id
  } : null
}
# Container Insights uses the AKS managed-identity authentication path enabled
# by oms_agent.msi_auth_for_monitoring_enabled. Azure may return no add-on
# identity in this mode; the supported onboarding does not require an explicit
# Monitoring Metrics Publisher assignment. Keep the DCR and association above.
resource "azurerm_monitor_metric_alert" "postgres_cpu" {
  count               = local.lab_count
  name                = "nk-dev-postgres-cpu"
  resource_group_name = azurerm_resource_group.platform.name
  scopes              = [azurerm_postgresql_flexible_server.database.id]
  severity            = 2
  frequency           = "PT1M"
  window_size         = "PT5M"
  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "cpu_percent"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }
  action { action_group_id = azurerm_monitor_action_group.lab[0].id }
}
resource "azurerm_role_assignment" "operator_prometheus" {
  count                = local.lab_count
  scope                = azurerm_monitor_workspace.lab[0].id
  role_definition_name = "Monitoring Data Reader"
  principal_id         = var.operator_object_id
  principal_type       = "User"
}

# One diagnostic setting per resource; no AllMetrics copies into LAW.
resource "azurerm_monitor_diagnostic_setting" "vault" {
  for_each                       = var.lab_enabled ? var.environments : toset([])
  name                           = "vault-audit-once"
  target_resource_id             = azurerm_key_vault.app[each.value].id
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.lab[0].id
  log_analytics_destination_type = "Dedicated"
  enabled_log { category = "AuditEvent" }
}
resource "azurerm_monitor_diagnostic_setting" "database" {
  count                          = local.lab_count
  name                           = "postgres-logs-once"
  target_resource_id             = azurerm_postgresql_flexible_server.database.id
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.lab[0].id
  log_analytics_destination_type = "Dedicated"
  enabled_log { category = "PostgreSQLLogs" }
}
resource "azurerm_monitor_diagnostic_setting" "cluster" {
  count                          = local.lab_count
  name                           = "aks-platform-errors-once"
  target_resource_id             = azurerm_kubernetes_cluster.platform.id
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.lab[0].id
  log_analytics_destination_type = "Dedicated"
  enabled_log { category = "kube-controller-manager" }
  enabled_log { category = "kube-scheduler" }
}
