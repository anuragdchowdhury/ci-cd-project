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
  default = "Standard_D4s_v4"
  validation {
    condition     = var.node_vm_size == "Standard_D4s_v4"
    error_message = "This quota-constrained Dev lab uses Standard_D4s_v4. Review quota before changing the SKU in code."
  }
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

variable "deployment_vm_enabled" {
  type    = bool
  default = false
}
variable "operator_ipv4" {
  type    = string
  default = ""
  validation {
    condition     = !var.deployment_vm_enabled || (can(cidrnetmask("${var.operator_ipv4}/32")) && !strcontains(var.operator_ipv4, "/"))
    error_message = "Supply one operator public IPv4 address, without a prefix."
  }
}
variable "ssh_public_key" {
  type    = string
  default = ""
  validation {
    condition     = !var.deployment_vm_enabled || startswith(var.ssh_public_key, "ssh-ed25519 ")
    error_message = "Supply an Ed25519 public SSH key. Never supply a private key."
  }
}
