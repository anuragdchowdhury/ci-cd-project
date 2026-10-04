# Built-in AKS RBAC Writer covers standard objects, but not application CRs
# such as SecretProviderClass. This supplementary grant stays namespace scoped.
# Without preview ABAC filtering it covers all namespaced CR kinds in Dev.
resource "azurerm_role_definition" "deployer_custom_resources" {
  name        = "${var.name_prefix}-${var.boundary}-application-custom-resources"
  scope       = azurerm_resource_group.platform.id
  description = "Read, write and delete namespaced application custom resources; assigned only to application namespaces."
  permissions {
    actions = []
    data_actions = [
      "Microsoft.ContainerService/managedClusters/customresources/read",
      "Microsoft.ContainerService/managedClusters/customresources/write",
      "Microsoft.ContainerService/managedClusters/customresources/delete",
    ]
  }
  assignable_scopes = [azurerm_resource_group.platform.id]
}

resource "azurerm_role_assignment" "deployer_custom_resources" {
  for_each           = var.environments
  scope              = "${azurerm_kubernetes_cluster.platform.id}/namespaces/notekeeper-${each.value}"
  role_definition_id = azurerm_role_definition.deployer_custom_resources.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.deployer[each.value].principal_id
  principal_type     = "ServicePrincipal"
}
