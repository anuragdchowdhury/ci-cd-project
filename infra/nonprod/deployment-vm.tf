# A VNet deployment executor, not a registered GitHub self-hosted runner.
# Two vCPUs + the two four-vCPU AKS nodes exhaust the recorded regional quota.
resource "azurerm_public_ip" "deployment" {
  count               = var.deployment_vm_enabled ? 1 : 0
  name                = "pip-${var.name_prefix}-dev-deploy"
  location            = var.location
  resource_group_name = module.platform.platform.resource_group
  allocation_method   = "Static"
  sku                 = "Standard"
}
resource "azurerm_network_security_group" "deployment" {
  count               = var.deployment_vm_enabled ? 1 : 0
  name                = "nsg-${var.name_prefix}-dev-deploy"
  location            = var.location
  resource_group_name = module.platform.platform.resource_group
  security_rule {
    name                       = "OperatorSSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "${var.operator_ipv4}/32"
    destination_address_prefix = "*"
  }
  # Override the default AllowVnetInBound rule for SSH too.
  security_rule {
    name                       = "DenyOtherSSH"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}
resource "azurerm_network_interface" "deployment" {
  count               = var.deployment_vm_enabled ? 1 : 0
  name                = "nic-${var.name_prefix}-dev-deploy"
  location            = var.location
  resource_group_name = module.platform.platform.resource_group
  ip_configuration {
    name                          = "primary"
    subnet_id                     = module.platform.platform.runner_subnet_id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.deployment[0].id
  }
}
resource "azurerm_network_interface_security_group_association" "deployment" {
  count                     = var.deployment_vm_enabled ? 1 : 0
  network_interface_id      = azurerm_network_interface.deployment[0].id
  network_security_group_id = azurerm_network_security_group.deployment[0].id
}
resource "azurerm_linux_virtual_machine" "deployment" {
  count                           = var.deployment_vm_enabled ? 1 : 0
  name                            = "vm-${var.name_prefix}-dev-deploy"
  location                        = var.location
  resource_group_name             = module.platform.platform.resource_group
  size                            = "Standard_D2s_v4"
  admin_username                  = "labadmin"
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.deployment[0].id]
  admin_ssh_key {
    username   = "labadmin"
    public_key = var.ssh_public_key
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [module.platform.platform.environments.dev.deployer_identity_id]
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 32
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
  # No credentials in cloud-init or Terraform state. CLI user login is temporary.
  custom_data = base64encode("#cloud-config\n${jsonencode({
    package_update = true
    packages       = ["ca-certificates", "curl", "git", "gnupg", "jq", "postgresql-client", "unzip", "python3"]
    write_files    = [{ path = "/opt/notekeeper/install-tools.sh", permissions = "0755", content = file("${path.module}/../../deploy/install-tools.sh") }]
    runcmd         = [["bash", "/opt/notekeeper/install-tools.sh"]]
  })}")
  depends_on = [azurerm_network_interface_security_group_association.deployment]
}
resource "azurerm_role_definition" "deployment_vm" {
  count       = var.deployment_vm_enabled ? 1 : 0
  name        = "${var.name_prefix}-dev-deployment-vm"
  scope       = "/subscriptions/${var.subscription_id}"
  description = "Invoke action Run Command and start/deallocate the single Dev executor VM."
  permissions {
    actions = [
      "Microsoft.Compute/virtualMachines/read",
      "Microsoft.Compute/virtualMachines/instanceView/read",
      "Microsoft.Compute/virtualMachines/runCommand/action",
      "Microsoft.Compute/virtualMachines/start/action",
      "Microsoft.Compute/virtualMachines/deallocate/action"
    ]
  }
  assignable_scopes = ["/subscriptions/${var.subscription_id}/resourceGroups/${module.platform.platform.resource_group}"]
}
resource "azurerm_role_assignment" "deployment_vm" {
  count              = var.deployment_vm_enabled ? 1 : 0
  scope              = azurerm_linux_virtual_machine.deployment[0].id
  role_definition_id = azurerm_role_definition.deployment_vm[0].role_definition_resource_id
  principal_id       = module.platform.platform.environments.dev.deployer_principal_id
  principal_type     = "ServicePrincipal"
}
output "deployment_vm" {
  value = var.deployment_vm_enabled ? {
    name           = azurerm_linux_virtual_machine.deployment[0].name
    resource_group = module.platform.platform.resource_group
    public_ip      = azurerm_public_ip.deployment[0].ip_address
    username       = "labadmin"
  } : null
}
