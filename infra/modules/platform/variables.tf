variable "subscription_id" { type = string }
variable "tenant_id" { type = string }
variable "location" { type = string }
variable "name_prefix" { type = string }
variable "boundary" { type = string }
variable "environments" { type = set(string) }
variable "vnet_cidr" { type = string }
variable "pod_cidr" { type = string }
variable "service_cidr" { type = string }
variable "kubernetes_version" { type = string }
variable "node_vm_size" { type = string }
variable "postgres_sku" { type = string }
variable "operator_object_id" { type = string }
variable "operator_login" {
  type = string
  validation {
    condition     = can(regex("^[[:ascii:]]+$", var.operator_login))
    error_message = "This lab's 63-byte PostgreSQL admin-name normalization requires an ASCII operator UPN."
  }
}
variable "registry_resource_id" { type = string }
variable "state_storage_account_id" { type = string }
variable "monthly_budget_amount" { type = number }
variable "budget_start_date" { type = string }
variable "alert_email" { type = string }
