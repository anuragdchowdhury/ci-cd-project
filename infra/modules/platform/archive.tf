# Optional archive is activated only after ContainerLogV2 exists. One export,
# not parallel diagnostic settings or a second collector.
resource "azurerm_storage_account" "logs" {
  count                           = var.lab_enabled && var.archive_enabled ? 1 : 0
  name                            = "st${var.name_prefix}logs${local.suffix}"
  resource_group_name             = azurerm_resource_group.platform.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices"]
    ip_rules       = [var.archive_operator_ipv4]
  }
  blob_properties {
    delete_retention_policy { days = 1 }
    container_delete_retention_policy { days = 1 }
  }
}
resource "azurerm_storage_management_policy" "logs" {
  count              = var.lab_enabled && var.archive_enabled ? 1 : 0
  storage_account_id = azurerm_storage_account.logs[0].id
  rule {
    name    = "expire-container-export"
    enabled = true
    filters {
      prefix_match = ["am-containerlogv2/"]
      blob_types   = ["blockBlob", "appendBlob"]
    }
    actions {
      base_blob { delete_after_days_since_modification_greater_than = 7 }
    }
  }
}
resource "azurerm_log_analytics_data_export_rule" "logs" {
  count                   = var.lab_enabled && var.archive_enabled ? 1 : 0
  name                    = "container-logs-once"
  resource_group_name     = azurerm_resource_group.platform.name
  workspace_resource_id   = azurerm_log_analytics_workspace.lab[0].id
  destination_resource_id = azurerm_storage_account.logs[0].id
  table_names             = ["ContainerLogV2"]
  enabled                 = true
}
resource "azurerm_role_assignment" "archive_operator" {
  count                = var.lab_enabled && var.archive_enabled ? 1 : 0
  scope                = azurerm_storage_account.logs[0].id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = var.operator_object_id
  principal_type       = "User"
}
resource "azurerm_log_analytics_workspace_table" "retention" {
  for_each                = var.lab_enabled && var.archive_enabled ? toset(["ContainerLogV2", "AppRequests", "AppDependencies"]) : toset([])
  workspace_id            = azurerm_log_analytics_workspace.lab[0].id
  name                    = each.value
  retention_in_days       = 30
  total_retention_in_days = 30
}
