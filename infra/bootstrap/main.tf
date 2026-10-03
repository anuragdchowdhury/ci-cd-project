locals {
  suffix = substr(sha256("${var.subscription_id}/${var.name_prefix}"), 0, 8)
  tags = {
    project     = "ci-cd-project"
    environment = "shared"
    owner       = "anuragdchowdhury"
    managed_by  = "terraform"
    purpose     = "lab-foundation"
  }
  state_containers = toset([
    "tfstate-bootstrap", "tfstate-registry", "tfstate-nonprod", "tfstate-prod"
  ])
  identities = {
    registry_infra = "infra-registry"
    publisher      = "acr-publish"
    check_reader   = "azure-oidc-check"
  }
  registry_scope   = var.registry_resource_id == null ? {} : { registry = var.registry_resource_id }
  repository_match = "(@Request[Microsoft.ContainerRegistry/registries/repositories:name] StringEqualsIgnoreCase 'notekeeper-backend' OR @Request[Microsoft.ContainerRegistry/registries/repositories:name] StringEqualsIgnoreCase 'notekeeper-frontend')"
}

resource "azurerm_resource_group" "bootstrap" {
  name     = "rg-${var.name_prefix}-bootstrap-ci"
  location = var.location
  tags     = local.tags
  lifecycle { prevent_destroy = true }
}

# Bootstrap owns this group; the registry root owns only the registry inside it.
resource "azurerm_resource_group" "registry" {
  name     = "rg-${var.name_prefix}-registry-ci"
  location = var.location
  tags     = local.tags
  lifecycle { prevent_destroy = true }
}

resource "azurerm_storage_account" "state" {
  name                            = "st${var.name_prefix}state${local.suffix}"
  resource_group_name             = azurerm_resource_group.bootstrap.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  default_to_oauth_authentication = true
  public_network_access           = "Enabled"
  tags                            = local.tags

  # An authenticated endpoint is temporarily reachable from one operator IP.
  # Private endpoint + private runner is a later, explicit networking transition.
  network_rules {
    default_action = "Deny"
    bypass         = ["None"]
    ip_rules       = [var.operator_public_ipv4]
  }

  blob_properties {
    versioning_enabled = true
    delete_retention_policy { days = 30 }
    container_delete_retention_policy { days = 30 }
  }
  lifecycle { prevent_destroy = true }
}

resource "azurerm_storage_container" "state" {
  for_each              = local.state_containers
  name                  = each.value
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
  lifecycle { prevent_destroy = true }
}

resource "azurerm_storage_management_policy" "state_history" {
  storage_account_id = azurerm_storage_account.state.id
  rule {
    name    = "expire-old-state-versions"
    enabled = true
    filters {
      blob_types   = ["blockBlob"]
      prefix_match = [for container in sort(tolist(local.state_containers)) : "${container}/"]
    }
    actions {
      # No base_blob deletion: the current state must survive indefinitely.
      version { delete_after_days_since_creation = 90 }
    }
  }
}

resource "azurerm_role_assignment" "operator_state" {
  for_each             = azurerm_storage_container.state
  scope                = each.value.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.operator_object_id
  principal_type       = "User"
}

resource "azurerm_management_lock" "state" {
  name       = "protect-terraform-state"
  scope      = azurerm_storage_account.state.id
  lock_level = "CanNotDelete"
  notes      = "Remove only through the documented, privileged lab teardown procedure."
  # Container creation and initial data-plane grants precede the account lock.
  depends_on = [azurerm_storage_container.state, azurerm_role_assignment.operator_state, azurerm_storage_management_policy.state_history]
}

resource "azurerm_user_assigned_identity" "github" {
  for_each            = local.identities
  name                = "id-${var.name_prefix}-${replace(each.key, "_", "-")}-ci"
  resource_group_name = azurerm_resource_group.bootstrap.name
  location            = var.location
  tags                = local.tags
}

resource "azurerm_federated_identity_credential" "github" {
  for_each                  = local.identities
  name                      = "github-${each.value}"
  user_assigned_identity_id = azurerm_user_assigned_identity.github[each.key].id
  issuer                    = "https://token.actions.githubusercontent.com"
  audience                  = ["api://AzureADTokenExchange"]
  subject                   = "repo:anuragdchowdhury@88018047/ci-cd-project@1401748151:environment:${each.value}"
}

resource "azurerm_role_assignment" "registry_infra" {
  scope                = azurerm_resource_group.registry.id
  role_definition_name = "Container Registry Contributor and Data Access Configuration Administrator"
  principal_id         = azurerm_user_assigned_identity.github["registry_infra"].principal_id
  principal_type       = "ServicePrincipal"
  description          = "Registry infrastructure only; no IAM or bootstrap administration."
}

resource "azurerm_role_assignment" "registry_infra_state" {
  scope                = azurerm_storage_container.state["tfstate-registry"].id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.github["registry_infra"].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "check_reader" {
  scope                = azurerm_resource_group.registry.id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.github["check_reader"].principal_id
  principal_type       = "ServicePrincipal"
}

# This diagnostic identity deliberately has no blob access: it runs on a
# GitHub-hosted runner which is outside the state account's allowed IP.
# Terraform jobs will use private runners once the networking stack exists.

resource "azurerm_role_assignment" "publisher" {
  for_each             = local.registry_scope
  scope                = each.value
  role_definition_name = "Container Registry Repository Writer"
  principal_id         = azurerm_user_assigned_identity.github["publisher"].principal_id
  principal_type       = "ServicePrincipal"
  condition_version    = "2.0"
  condition            = <<-EOT
    ((!(ActionMatches{'Microsoft.ContainerRegistry/registries/repositories/content/read'})
      AND !(ActionMatches{'Microsoft.ContainerRegistry/registries/repositories/content/write'})
      AND !(ActionMatches{'Microsoft.ContainerRegistry/registries/repositories/metadata/read'})
      AND !(ActionMatches{'Microsoft.ContainerRegistry/registries/repositories/metadata/write'}))
      OR ${local.repository_match})
  EOT
}

resource "azurerm_role_assignment" "publisher_configuration_reader" {
  for_each             = local.registry_scope
  scope                = each.value
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.github["publisher"].principal_id
  principal_type       = "ServicePrincipal"
  description          = "Read registry configuration for az acr login; cannot modify the registry."
}

resource "azurerm_role_assignment" "operator_image_reader" {
  for_each             = local.registry_scope
  scope                = each.value
  role_definition_name = "Container Registry Repository Reader"
  principal_id         = var.operator_object_id
  principal_type       = "User"
  condition_version    = "2.0"
  condition            = <<-EOT
    ((!(ActionMatches{'Microsoft.ContainerRegistry/registries/repositories/content/read'})
      AND !(ActionMatches{'Microsoft.ContainerRegistry/registries/repositories/metadata/read'}))
      OR ${local.repository_match})
  EOT
}
