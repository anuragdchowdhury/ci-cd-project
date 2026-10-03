locals {
  suffix           = substr(sha256("${var.subscription_id}/${var.name_prefix}/${var.boundary}"), 0, 8)
  tags             = { project = "ci-cd-project", environment = var.boundary, managed_by = "terraform", purpose = "hands-on" }
  repository_match = "(@Request[Microsoft.ContainerRegistry/registries/repositories:name] StringEqualsIgnoreCase 'notekeeper-backend' OR @Request[Microsoft.ContainerRegistry/registries/repositories:name] StringEqualsIgnoreCase 'notekeeper-frontend')"
}
resource "azurerm_resource_group" "platform" {
  name     = "rg-${var.name_prefix}-${var.boundary}"
  location = var.location
  tags     = local.tags
}
resource "azurerm_virtual_network" "platform" {
  name                = "vnet-${var.name_prefix}-${var.boundary}"
  location            = var.location
  resource_group_name = azurerm_resource_group.platform.name
  address_space       = [var.vnet_cidr]
  tags                = local.tags
}
resource "azurerm_subnet" "nodes" {
  name                 = "aks-nodes"
  resource_group_name  = azurerm_resource_group.platform.name
  virtual_network_name = azurerm_virtual_network.platform.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 4, 0)]
}
resource "azurerm_subnet" "database" {
  name                 = "postgres"
  resource_group_name  = azurerm_resource_group.platform.name
  virtual_network_name = azurerm_virtual_network.platform.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 8, 16)]
  service_endpoint { service = "Microsoft.Storage" }
  delegation {
    name = "postgres"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}
resource "azurerm_subnet" "endpoints" {
  name                 = "private-endpoints"
  resource_group_name  = azurerm_resource_group.platform.name
  virtual_network_name = azurerm_virtual_network.platform.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 8, 17)]
}
# Reserved now; a later PR adds the ephemeral deployment runner here.
resource "azurerm_subnet" "runner" {
  name                 = "deployment-runner"
  resource_group_name  = azurerm_resource_group.platform.name
  virtual_network_name = azurerm_virtual_network.platform.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 8, 18)]
  service_endpoint { service = "Microsoft.Storage" }
}
resource "azurerm_subnet" "ingress" {
  name                                          = "ingress-private-link"
  resource_group_name                           = azurerm_resource_group.platform.name
  virtual_network_name                          = azurerm_virtual_network.platform.name
  address_prefixes                              = [cidrsubnet(var.vnet_cidr, 8, 19)]
  private_link_service_network_policies_enabled = false
}
resource "azurerm_user_assigned_identity" "control_plane" {
  name                = "id-${var.name_prefix}-${var.boundary}-aks"
  location            = var.location
  resource_group_name = azurerm_resource_group.platform.name
  tags                = local.tags
}
resource "azurerm_user_assigned_identity" "kubelet" {
  name                = "id-${var.name_prefix}-${var.boundary}-kubelet"
  location            = var.location
  resource_group_name = azurerm_resource_group.platform.name
  tags                = local.tags
}
resource "azurerm_role_assignment" "cluster_network" {
  scope                = azurerm_virtual_network.platform.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_user_assigned_identity.control_plane.principal_id
  principal_type       = "ServicePrincipal"
}
resource "azurerm_role_assignment" "kubelet_identity" {
  scope                = azurerm_user_assigned_identity.kubelet.id
  role_definition_name = "Managed Identity Operator"
  principal_id         = azurerm_user_assigned_identity.control_plane.principal_id
  principal_type       = "ServicePrincipal"
}
resource "azurerm_role_assignment" "image_pull" {
  scope                = var.registry_resource_id
  role_definition_name = "Container Registry Repository Reader"
  principal_id         = azurerm_user_assigned_identity.kubelet.principal_id
  principal_type       = "ServicePrincipal"
  condition_version    = "2.0"
  condition            = <<-EOT
    ((!(ActionMatches{'Microsoft.ContainerRegistry/registries/repositories/content/read'})
      AND !(ActionMatches{'Microsoft.ContainerRegistry/registries/repositories/metadata/read'}))
      OR ${local.repository_match})
  EOT
}
resource "azurerm_kubernetes_cluster" "platform" {
  name                                = "aks-notekeeper-${var.boundary}"
  location                            = var.location
  resource_group_name                 = azurerm_resource_group.platform.name
  node_resource_group                 = "rg-${var.name_prefix}-${var.boundary}-nodes"
  dns_prefix                          = "${var.name_prefix}-${var.boundary}-${local.suffix}"
  kubernetes_version                  = var.kubernetes_version
  sku_tier                            = "Free"
  private_cluster_enabled             = true
  private_cluster_public_fqdn_enabled = false
  private_dns_zone_id                 = "System"
  local_account_disabled              = true
  role_based_access_control_enabled   = true
  oidc_issuer_enabled                 = true
  workload_identity_enabled           = true
  run_command_enabled                 = false
  azure_active_directory_role_based_access_control {
    tenant_id          = var.tenant_id
    azure_rbac_enabled = true
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.control_plane.id]
  }
  kubelet_identity {
    client_id                 = azurerm_user_assigned_identity.kubelet.client_id
    object_id                 = azurerm_user_assigned_identity.kubelet.principal_id
    user_assigned_identity_id = azurerm_user_assigned_identity.kubelet.id
  }
  node_provisioning_profile {
    mode               = "Manual"
    default_node_pools = "None"
  }
  default_node_pool {
    name                 = "system"
    vm_size              = var.node_vm_size
    vnet_subnet_id       = azurerm_subnet.nodes.id
    auto_scaling_enabled = true
    min_count            = 1
    max_count            = 2
    max_pods             = 50
    os_disk_size_gb      = 64
    os_sku               = "Ubuntu"
    upgrade_settings { max_surge = "1" }
  }
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_data_plane  = "cilium"
    load_balancer_sku   = "standard"
    outbound_type       = "loadBalancer"
    pod_cidr            = var.pod_cidr
    service_cidr        = var.service_cidr
    dns_service_ip      = cidrhost(var.service_cidr, 10)
  }
  key_vault_secrets_provider {
    secret_rotation_enabled  = true
    secret_rotation_interval = "2m"
  }
  tags       = local.tags
  depends_on = [azurerm_role_assignment.cluster_network, azurerm_role_assignment.kubelet_identity, azurerm_role_assignment.image_pull]
}
resource "azurerm_role_assignment" "operator_cluster_admin" {
  scope                = azurerm_kubernetes_cluster.platform.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = var.operator_object_id
  principal_type       = "User"
}
resource "azurerm_private_dns_zone" "postgres" {
  name                = "${var.name_prefix}-${var.boundary}.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.platform.name
  tags                = local.tags
}
resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                 = "postgres-vnet"
  private_dns_zone_id  = azurerm_private_dns_zone.postgres.id
  virtual_network_id   = azurerm_virtual_network.platform.id
  registration_enabled = false
}
resource "azurerm_postgresql_flexible_server" "database" {
  name                          = "pg-${var.name_prefix}-${var.boundary}-${local.suffix}"
  resource_group_name           = azurerm_resource_group.platform.name
  location                      = var.location
  version                       = "16"
  sku_name                      = var.postgres_sku
  storage_mb                    = 32768
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = false
  delegated_subnet_id           = azurerm_subnet.database.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = var.tenant_id
  }
  tags       = local.tags
  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}
resource "azurerm_postgresql_flexible_server_active_directory_administrator" "operator" {
  server_name         = azurerm_postgresql_flexible_server.database.name
  resource_group_name = azurerm_resource_group.platform.name
  tenant_id           = var.tenant_id
  object_id           = var.operator_object_id
  principal_name      = var.operator_login
  principal_type      = "User"
}
resource "azurerm_postgresql_flexible_server_database" "app" {
  for_each  = var.environments
  name      = "notekeeper_${each.value}"
  server_id = azurerm_postgresql_flexible_server.database.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}
resource "azurerm_private_dns_zone" "endpoint" {
  for_each            = toset(["privatelink.vaultcore.azure.net", "privatelink.blob.core.windows.net"])
  name                = each.value
  resource_group_name = azurerm_resource_group.platform.name
  tags                = local.tags
}
resource "azurerm_private_dns_zone_virtual_network_link" "endpoint" {
  for_each             = azurerm_private_dns_zone.endpoint
  name                 = "endpoint-vnet"
  private_dns_zone_id  = each.value.id
  virtual_network_id   = azurerm_virtual_network.platform.id
  registration_enabled = false
}
resource "azurerm_key_vault" "app" {
  for_each                      = var.environments
  name                          = "kv-${var.name_prefix}-${each.value}-${local.suffix}"
  resource_group_name           = azurerm_resource_group.platform.name
  location                      = var.location
  tenant_id                     = var.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  public_network_access_enabled = false
  soft_delete_retention_days    = 7
  purge_protection_enabled      = true
  tags                          = merge(local.tags, { environment = each.value })
}
resource "azurerm_private_endpoint" "vault" {
  for_each            = var.environments
  name                = "pe-kv-${each.value}"
  resource_group_name = azurerm_resource_group.platform.name
  location            = var.location
  subnet_id           = azurerm_subnet.endpoints.id
  private_service_connection {
    name                           = "vault"
    private_connection_resource_id = azurerm_key_vault.app[each.value].id
    is_manual_connection           = false
    subresource_names              = ["vault"]
  }
  private_dns_zone_group {
    name                 = "vault"
    private_dns_zone_ids = [azurerm_private_dns_zone.endpoint["privatelink.vaultcore.azure.net"].id]
  }
  tags = local.tags
}
resource "azurerm_private_endpoint" "state" {
  name                = "pe-terraform-state"
  resource_group_name = azurerm_resource_group.platform.name
  location            = var.location
  subnet_id           = azurerm_subnet.endpoints.id
  private_service_connection {
    name                           = "state"
    private_connection_resource_id = var.state_storage_account_id
    is_manual_connection           = false
    subresource_names              = ["blob"]
  }
  private_dns_zone_group {
    name                 = "blob"
    private_dns_zone_ids = [azurerm_private_dns_zone.endpoint["privatelink.blob.core.windows.net"].id]
  }
  tags = local.tags
}
resource "azurerm_role_assignment" "operator_secrets" {
  for_each             = var.environments
  scope                = azurerm_key_vault.app[each.value].id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = var.operator_object_id
  principal_type       = "User"
}
resource "azurerm_user_assigned_identity" "runtime" {
  for_each            = var.environments
  name                = "id-${var.name_prefix}-${each.value}-api"
  location            = var.location
  resource_group_name = azurerm_resource_group.platform.name
  tags                = merge(local.tags, { environment = each.value })
}
resource "azurerm_user_assigned_identity" "migration" {
  for_each            = var.environments
  name                = "id-${var.name_prefix}-${each.value}-migration"
  location            = var.location
  resource_group_name = azurerm_resource_group.platform.name
  tags                = merge(local.tags, { environment = each.value })
}
resource "azurerm_federated_identity_credential" "runtime" {
  for_each                  = var.environments
  name                      = "aks-api"
  user_assigned_identity_id = azurerm_user_assigned_identity.runtime[each.value].id
  issuer                    = azurerm_kubernetes_cluster.platform.oidc_issuer_url
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "system:serviceaccount:notekeeper-${each.value}:notekeeper-api"
}
resource "azurerm_federated_identity_credential" "migration" {
  for_each                  = var.environments
  name                      = "aks-migration"
  user_assigned_identity_id = azurerm_user_assigned_identity.migration[each.value].id
  issuer                    = azurerm_kubernetes_cluster.platform.oidc_issuer_url
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "system:serviceaccount:notekeeper-${each.value}:notekeeper-migration"
}
resource "azurerm_role_assignment" "runtime_secrets" {
  for_each             = var.environments
  scope                = azurerm_key_vault.app[each.value].id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.runtime[each.value].principal_id
  principal_type       = "ServicePrincipal"
}
resource "azurerm_user_assigned_identity" "deployer" {
  for_each            = var.environments
  name                = "id-${var.name_prefix}-${each.value}-deploy"
  location            = var.location
  resource_group_name = azurerm_resource_group.platform.name
  tags                = merge(local.tags, { environment = each.value })
}
resource "azurerm_federated_identity_credential" "deployer" {
  for_each                  = var.environments
  name                      = "github-${each.value}"
  user_assigned_identity_id = azurerm_user_assigned_identity.deployer[each.value].id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "repo:anuragdchowdhury@88018047/ci-cd-project@1401748151:environment:${each.value}"
}
resource "azurerm_role_assignment" "deployer_credentials" {
  for_each             = var.environments
  scope                = azurerm_kubernetes_cluster.platform.id
  role_definition_name = "Azure Kubernetes Service Cluster User Role"
  principal_id         = azurerm_user_assigned_identity.deployer[each.value].principal_id
  principal_type       = "ServicePrincipal"
}
resource "azurerm_role_assignment" "deployer_namespace" {
  for_each             = var.environments
  scope                = "${azurerm_kubernetes_cluster.platform.id}/namespaces/notekeeper-${each.value}"
  role_definition_name = "Azure Kubernetes Service RBAC Writer"
  principal_id         = azurerm_user_assigned_identity.deployer[each.value].principal_id
  principal_type       = "ServicePrincipal"
}
resource "azurerm_consumption_budget_resource_group" "platform" {
  name              = "budget-${var.name_prefix}-${var.boundary}"
  resource_group_id = azurerm_resource_group.platform.id
  amount            = var.monthly_budget_amount
  time_grain        = "Monthly"
  time_period { start_date = var.budget_start_date }
  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }
  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Forecasted"
    contact_emails = [var.alert_email]
  }
}
# AKS nodes live in a separate managed resource group; budget that spend too.
resource "azurerm_consumption_budget_resource_group" "nodes" {
  name              = "budget-${var.name_prefix}-${var.boundary}-nodes"
  resource_group_id = "/subscriptions/${var.subscription_id}/resourceGroups/${azurerm_kubernetes_cluster.platform.node_resource_group}"
  amount            = var.monthly_budget_amount
  time_grain        = "Monthly"
  time_period { start_date = var.budget_start_date }
  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }
}
