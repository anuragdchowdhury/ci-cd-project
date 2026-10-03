variable "subscription_id" { type = string }
variable "tenant_id" { type = string }
variable "location" {
  type    = string
  default = "centralindia"
}
variable "name_prefix" {
  type    = string
  default = "nk"
}
variable "registry_resource_id" { type = string }
variable "state_storage_account_id" { type = string }
variable "operator_object_id" { type = string }
variable "operator_login" { type = string }
variable "kubernetes_version" {
  type        = string
  description = "Select a supported GA version from az aks get-versions; do not guess a version."
}
variable "node_vm_size" {
  type    = string
  default = "Standard_D4s_v5"
}
variable "postgres_sku" {
  type    = string
  default = "B_Standard_B1ms"
}
variable "monthly_budget_amount" {
  type        = number
  description = "Per-resource-group alert threshold, in the subscription billing currency; not a spend cap."
  validation {
    condition     = var.monthly_budget_amount > 0
    error_message = "Set a positive budget threshold."
  }
}
variable "alert_email" {
  type = string
  validation {
    condition     = can(regex("^[^@ ]+@[^@ ]+\\.[^@ ]+$", var.alert_email))
    error_message = "Supply your budget notification email."
  }
}
variable "budget_start_date" {
  type        = string
  description = "First day of the current month, UTC: YYYY-MM-01T00:00:00Z. Keep it stable after creation."
}
