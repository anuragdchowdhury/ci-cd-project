output "platform" {
  value = {
    resource_group    = azurerm_resource_group.platform.name
    vnet_id           = azurerm_virtual_network.platform.id
    runner_subnet_id  = azurerm_subnet.runner.id
    ingress_subnet_id = azurerm_subnet.ingress.id
    cluster_name      = azurerm_kubernetes_cluster.platform.name
    cluster_id        = azurerm_kubernetes_cluster.platform.id
    private_api_fqdn  = azurerm_kubernetes_cluster.platform.private_fqdn
    oidc_issuer_url   = azurerm_kubernetes_cluster.platform.oidc_issuer_url
    postgres_name     = azurerm_postgresql_flexible_server.database.name
    postgres_fqdn     = azurerm_postgresql_flexible_server.database.fqdn
    environments = {
      for env in var.environments : env => {
        namespace               = "notekeeper-${env}"
        database                = azurerm_postgresql_flexible_server_database.app[env].name
        vault_name              = azurerm_key_vault.app[env].name
        runtime_client_id       = azurerm_user_assigned_identity.runtime[env].client_id
        runtime_principal_id    = azurerm_user_assigned_identity.runtime[env].principal_id
        runtime_identity_name   = azurerm_user_assigned_identity.runtime[env].name
        migration_client_id     = azurerm_user_assigned_identity.migration[env].client_id
        migration_principal_id  = azurerm_user_assigned_identity.migration[env].principal_id
        migration_identity_name = azurerm_user_assigned_identity.migration[env].name
        deployer_client_id      = azurerm_user_assigned_identity.deployer[env].client_id
      }
    }
  }
}
