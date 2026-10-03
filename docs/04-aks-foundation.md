# 04 — Provision the AKS and database foundation

This checkpoint creates Azure resources, not a running website. Start with nonprod; provision prod after nonprod deployment works. Terraform runs from your authenticated laptop for this checkpoint. Cloud APIs are reachable from your laptop; private AKS, database and Key Vault data endpoints are not. The next checkpoint supplies private runner/operator access, namespace bootstrap, SQL grants and Helm. We do not temporarily expose those services to make a test pass.

## What this PR creates and why

| Component | Nonprod | Prod (later) | Purpose |
|---|---|---|---|
| Resource group / VNet | `rg-nk-nonprod`, `10.20.0.0/16` | `rg-nk-prod`, `10.30.0.0/16` | Separate ownership and network boundaries; no peering |
| Private AKS | `aks-notekeeper-nonprod` | `aks-notekeeper-prod` | Dev/staging share a cluster; prod is separate |
| System pool | D4s_v5, autoscaler 1–2 nodes | Same small lab settings | Current system-pool minimum is four vCPUs; one node is a lab compromise, not HA |
| PostgreSQL 16 | B1ms, 32 GiB, dev/staging databases | Separate B1ms server/database | Private networking, Entra-only authentication, seven-day backups; HA off |
| Key Vault | One each for dev/staging | One for prod | Private endpoints, RBAC, seven-day soft delete/purge protection |
| Runtime/migration identities | Separate per environment and purpose | Separate prod identities | AKS federation; runtime reads only its own vault; SQL privileges are added next |
| Deploy identities | Dev/staging namespace RBAC | Prod namespace RBAC | GitHub environment OIDC, no cloud secret; namespaces are created next |
| Kubelet identity | Two-repository ACR Reader | Separate two-repository Reader | Pulls images without registry passwords or imagePullSecrets |
| Private state endpoints | Blob endpoint/DNS in each VNet | Same | Future private runners can reach remote state without opening the storage firewall |
| Reserved subnets | Runner and ingress/Private Link | Same | Keep subsequent private runner and Front Door work in this network |
| Budget alerts | Platform and AKS node groups separately | Same | Email alerts; each group has its own threshold, not one combined budget or spend cap |

Pods use Azure CNI Overlay + Cilium. Egress uses an AKS-managed standard load balancer; private API does not mean no outbound Internet. AKS creates/owns its node resource group, disks, API private DNS and load-balancer components. Terraform owns our cluster/network declaration; do not manually change AKS-managed resources.

There is no Front Door, Grafana, DCR, telemetry collection, application deployment, SQL principal registration or deployment runner yet. These remain the following milestones. Dev/staging SQL isolation must be validated after grants; creating two databases alone is not sufficient.

## 1. Merge after checks pass

Merge the foundation PR after its four Terraform checks pass. Then:

```bash
git switch main
git pull --ff-only
az account set --subscription b4207b90-6a00-470a-aa95-b154c688bb74
az account show --query '{subscription:id,tenant:tenantId,state:state}' -o table
```

Keep using the operator account with Owner access for these initial resource/role assignments. The eventual application deploy identities have namespace scope; they cannot create infrastructure or grant IAM.

## 2. Reconcile the catalog role you added in the portal

Import the existing assignment instead of creating a duplicate. Your original ignored bootstrap variables and backend must still be present. Do not run init -migrate-state again merely because this PR adds roots.

```bash
CATALOG_ROLE_ID=$(az role assignment list \
  --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --scope /subscriptions/b4207b90-6a00-470a-aa95-b154c688bb74/resourceGroups/rg-nk-registry-ci/providers/Microsoft.ContainerRegistry/registries/acrnk81c108fc \
  --query "[?roleDefinitionName=='Container Registry Repository Catalog Lister'].id | [0]" -o tsv)
```

If this is empty, confirm you assigned the role to the same account used by Azure CLI. If it contains a role-assignment resource ID:

```bash
terraform -chdir=infra/bootstrap import \
  'azurerm_role_assignment.operator_catalog_lister["registry"]' "$CATALOG_ROLE_ID"
terraform -chdir=infra/bootstrap plan
```

Expect no changes to the existing bootstrap resources after import. If Terraform reports another unexpected change, resolve it before applying; do not blindly approve it. No bootstrap apply is needed for an assignment already imported successfully.

## 3. Register providers and check capacity

```bash
for provider in Microsoft.Compute Microsoft.Network Microsoft.ContainerService Microsoft.DBforPostgreSQL Microsoft.KeyVault Microsoft.ManagedIdentity Microsoft.Consumption; do
  az provider register --namespace "$provider"
done
az provider list --query "[?namespace=='Microsoft.Compute' || namespace=='Microsoft.Network' || namespace=='Microsoft.ContainerService' || namespace=='Microsoft.DBforPostgreSQL' || namespace=='Microsoft.KeyVault' || namespace=='Microsoft.ManagedIdentity' || namespace=='Microsoft.Consumption'].{provider:namespace,state:registrationState}" -o table
az aks get-versions --location centralindia -o table
az vm list-skus --location centralindia --size Standard_D4s_v5 --all \
  --query "[?name=='Standard_D4s_v5'].{name:name,restrictions:restrictions}" -o json
az vm list-usage --location centralindia -o table
az postgres flexible-server list-skus --location centralindia -o table
```

Wait until registrations show Registered. Choose an available GA AKS patch version from the output; record the exact version rather than selecting a preview or guessing. D4s_v5 must not have a subscription restriction. Confirm B1ms is available. SKU discovery does not guarantee regional capacity at apply time.

Allow headroom for scale-out and rolling upgrade: each D4s_v5 uses four vCPUs, each cluster can reach two nodes and temporarily add one surge node. Two clusters can therefore need up to 24 vCPUs in the family/regional quotas, before runner VMs or other resources. Initially nonprod starts with only one four-vCPU node. Request quota or choose another available supported four-vCPU SKU if needed; update the ignored inputs before plan.

Before apply, use https://azure.microsoft.com/pricing/calculator/ to estimate Central India D4s_v5 Linux nodes (one normally, up to three during an upgrade), PostgreSQL B1ms + 32 GiB storage, private endpoints, load balancer/disks and networking. Check the subscription's billing currency. Later include Front Door Premium, Grafana, telemetry and private runners; they are not covered by this checkpoint's estimate. Budget alerts notify, never shut resources down. Do not treat the budget amount below as an estimated bill.

## 4. Generate ignored configuration

The existing generator now also writes nonprod/prod backend files, pointing to your already-created containers. This command does not migrate or modify remote state:

```bash
terraform -chdir=infra/bootstrap output -json configuration | python3 scripts/configure_azure_backend.py
```

Replace the three values below. The budget is an alert threshold in your subscription's billing currency, separately for each resource group. Use an email you control. The script checks the Azure CLI subscription/tenant and records your signed-in Entra user as the DB administrator.

```bash
terraform -chdir=infra/bootstrap output -json configuration | \
  python3 scripts/configure_platform.py \
    --kubernetes-version 'REPLACE_WITH_SUPPORTED_GA_PATCH' \
    --budget-amount REPLACE_WITH_POSITIVE_NUMBER \
    --alert-email 'REPLACE_WITH_YOUR_EMAIL'
```

Review `infra/.generated/nonprod.auto.tfvars.json`. It contains identifiers/configuration, not credentials, and is ignored by Git. Do not publish plans or full state. Keep your existing operator IPv4 storage firewall rule current if your public IP changed.

## 5. Plan, review and apply nonprod

```bash
terraform -chdir=infra/nonprod init -input=false \
  -backend-config=../.generated/nonprod.backend.hcl
terraform -chdir=infra/nonprod validate
terraform -chdir=infra/nonprod plan \
  -var-file=../.generated/nonprod.auto.tfvars.json \
  -out=nonprod.tfplan
terraform -chdir=infra/nonprod show -no-color nonprod.tfplan
```

The first plan should add resources for nonprod and add no prod resources. It must not destroy/replace your bootstrap storage or registry: this root owns neither. Review the private API, Entra-only PostgreSQL, SKU, vault public access disabled, repository-conditioned image Reader and namespace deploy scopes.

Then apply the exact reviewed plan (this starts billable Azure resources):

```bash
terraform -chdir=infra/nonprod apply nonprod.tfplan
terraform -chdir=infra/nonprod output -json platform
terraform -chdir=infra/nonprod plan \
  -var-file=../.generated/nonprod.auto.tfvars.json
```

Expect No changes on the follow-up plan. Creation can take tens of minutes. If a capacity, quota or permissions error occurs, retain the remote state; diagnose and re-plan after fixing it. Do not delete state or repeatedly create a new stack.

## 6. Validate the Azure foundation

```bash
az aks show -g rg-nk-nonprod -n aks-notekeeper-nonprod \
  --query '{state:provisioningState,privateAPI:apiServerAccessProfile.enablePrivateCluster,localAccountsDisabled:disableLocalAccounts,oidc:oidcIssuerProfile.enabled,workloadIdentity:securityProfile.workloadIdentity.enabled,pools:agentPoolProfiles[].{name:name,size:vmSize,count:count,min:minCount,max:maxCount}}' -o json
az postgres flexible-server list -g rg-nk-nonprod \
  --query '[].{name:name,state:state,publicAccess:network.publicNetworkAccess,authentication:authConfig}' -o json
az keyvault list -g rg-nk-nonprod --query '[].{name:name,publicAccess:properties.publicNetworkAccess,rbac:properties.enableRbacAuthorization}' -o json
az network private-endpoint list -g rg-nk-nonprod \
  --query '[].{name:name,state:provisioningState,connections:privateLinkServiceConnections[].privateLinkServiceConnectionState.status}' -o json
```

Look for succeeded/ready resources, private AKS enabled, workload identity enabled, local accounts disabled, PostgreSQL public access disabled/password auth disabled, and Approved private endpoint connections.

This proves Azure provisioning, not end-to-end connectivity. `kubectl` from your laptop and reading Key Vault secrets should not work without private network access. At the next checkpoint, we verify DNS resolves privately from the runner, image pulls succeed, register DB principals, apply namespace permissions and deploy dev.

Share the **nonsecret output of `terraform output -json platform`**, the Azure checks above and the follow-up plan summary. Do not send state, plans, access tokens or kubeconfig.

## Prod and shutdown

Do not provision prod just to check the code; CI already validates its schema. Once nonprod works, repeat step 5 with `prod` paths/files, then apply its separately reviewed plan. Never point the prod backend at the nonprod container.

For a pause, stopping AKS and PostgreSQL saves some compute charges but storage, private endpoints and networking continue billing. For permanent cleanup later, remove Helm/Front Door/runner dependencies first, then use `terraform destroy -var-file=../.generated/nonprod.auto.tfvars.json` in this root. Review the destroy plan. Key Vault purge protection means deleted vault names cannot immediately be reused; recover the vault or wait for retention. Never destroy the bootstrap state storage as part of this cleanup.

## References

- System pools and minimum VM sizing: https://learn.microsoft.com/azure/aks/use-system-pools
- Workload identity: https://learn.microsoft.com/azure/aks/workload-identity-deploy-cluster
- PostgreSQL private networking: https://learn.microsoft.com/azure/postgresql/network/concepts-networking-private
- ACR ABAC permissions: https://learn.microsoft.com/azure/container-registry/container-registry-rbac-abac-repository-permissions
