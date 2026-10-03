output "configuration" {
  description = "Nonsecret identifiers for backend configuration and GitHub repository variables."
  value = {
    subscription_id          = var.subscription_id
    tenant_id                = var.tenant_id
    location                 = var.location
    name_prefix              = var.name_prefix
    storage_account_name     = azurerm_storage_account.state.name
    bootstrap_resource_group = azurerm_resource_group.bootstrap.name
    registry_resource_group  = azurerm_resource_group.registry.name
    registry_name            = "acr${var.name_prefix}${local.suffix}"
    github_repository        = var.github_repository
    github_identities = {
      for key, identity in azurerm_user_assigned_identity.github : key => {
        client_id    = identity.client_id
        principal_id = identity.principal_id
        environment  = local.identities[key]
      }
    }
  }
}
