module "platform" {
  source                   = "../modules/platform"
  boundary                 = "nonprod"
  environments             = ["dev", "staging"]
  vnet_cidr                = "10.20.0.0/16"
  pod_cidr                 = "10.240.0.0/16"
  service_cidr             = "10.100.0.0/16"
  subscription_id          = var.subscription_id
  tenant_id                = var.tenant_id
  location                 = var.location
  name_prefix              = var.name_prefix
  registry_resource_id     = var.registry_resource_id
  state_storage_account_id = var.state_storage_account_id
  operator_object_id       = var.operator_object_id
  operator_login           = var.operator_login
  kubernetes_version       = var.kubernetes_version
  node_vm_size             = var.node_vm_size
  postgres_sku             = var.postgres_sku
  monthly_budget_amount    = var.monthly_budget_amount
  budget_start_date        = var.budget_start_date
  alert_email              = var.alert_email
}
output "platform" { value = module.platform.platform }
