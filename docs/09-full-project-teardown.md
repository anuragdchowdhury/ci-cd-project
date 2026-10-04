# Future full NoteKeeper teardown

**Do not execute this runbook while learning or testing.** Merging this document does not delete anything. Execute it deliberately before the credits expire on 6 October 2026; allow time on 5 October for deletion failures. Stopping AKS or deallocating the VM is not full cleanup: disks, Front Door, Grafana, PostgreSQL, ACR and storage can remain billable.

This procedure is for subscription `b4207b90-6a00-470a-aa95-b154c688bb74` and this project's four Terraform roots only. Keep the GitHub repository, local code and Namecheap domain. Do not delete the subscription, tenant, unrelated resource groups, or resource providers. No staging or production deployment is expected; an unexpected prod state requires separate review.

## 1. Freeze changes and establish ownership

Run on the Mac in the repository, using the operator's normal Azure login. Cancel or finish active deployment/build workflows first. Disable only the Azure-dependent workflows during cleanup:

```bash
gh workflow disable deploy-dev.yml --repo anuragdchowdhury/ci-cd-project
gh workflow disable ci.yml --repo anuragdchowdhury/ci-cd-project
gh workflow disable azure-oidc-check.yml --repo anuragdchowdhury/ci-cd-project
az account set --subscription b4207b90-6a00-470a-aa95-b154c688bb74
mkdir -p reports
python3 scripts/teardown_inventory.py > reports/teardown-before.json
```

The inventory is read-only. Review every resource in `rg-nk-nonprod`, `rg-nk-nonprod-nodes`, `rg-nk-registry-ci`, `rg-nk-bootstrap-ci` and the exact Monitor workspace managed group. Compare IDs with `terraform state list` and `terraform state show ADDRESS` for each root. Kubernetes-created load balancer resources belong to the AKS deployment but are not necessarily individual Terraform entries. **Stop if any group contains an unrelated resource.** Deleting a Terraform-owned resource group also deletes its contents, including resources outside Terraform.

Capture project IAM role-definition IDs from state too: resource-group inventory does not enumerate all subscription-scoped custom roles. Never delete a resource because its name merely starts with `nk`, `MC_` or `MA_`.

## 2. Preserve state and required evidence

All four roots must be connected to their existing backends, not initialized into new empty state. Keep the generated inputs used for the actual deployment. Do not regenerate them with different defaults just to get a destroy plan.

If backend files are missing, reconnect bootstrap using the existing `stnkstate81c108fc` account and `tfstate-bootstrap/terraform.tfstate`, following docs/02. Then:

```bash
terraform -chdir=infra/bootstrap output -json configuration |
  python3 scripts/configure_azure_backend.py
```

This recreates backend files and registry inputs. It does not recreate nonprod/access/lab inputs. Recover those from your original local deployment inputs before continuing. Retain the original ignored `infra/bootstrap/terraform.tfvars`, including operator object ID, current allowed IPv4 and the exact registry resource ID.

Initialize each root against its existing state (bootstrap already reconnected):

```bash
terraform -chdir=infra/edge init -reconfigure -backend-config=../.generated/edge.backend.hcl
terraform -chdir=infra/nonprod init -reconfigure -backend-config=../.generated/nonprod.backend.hcl
terraform -chdir=infra/registry init -reconfigure -backend-config=../.generated/registry.backend.hcl
```

Ensure your public IPv4 still matches the storage firewall; use the existing bootstrap access procedure if it changed. Do not open storage to everyone.

Create private local backups outside the repository:

```bash
umask 077
TEARDOWN_BACKUP="$HOME/notekeeper-teardown-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$TEARDOWN_BACKUP"
for stack in edge nonprod registry bootstrap; do
  terraform -chdir="infra/$stack" state pull > "$TEARDOWN_BACKUP/$stack.tfstate" || break
done
```

Confirm all four backups exist, are nonempty and contain the expected resource addresses. If any command failed, stop. State can contain sensitive information: do not commit, upload as a GitHub artifact, or paste it into chat. Export any notes or screenshots you want before database/log deletion. Inspect `tfstate-prod` for unexpected state before deleting the storage account; an unused container is expected, deployed prod resources are not.

## 3. Remove Front Door and its private ingress connection

```bash
terraform -chdir=infra/edge plan -destroy -var-file=../.generated/edge.auto.tfvars.json -out=teardown-edge.tfplan
terraform -chdir=infra/edge show -no-color teardown-edge.tfplan
# Only after reviewing every deletion:
terraform -chdir=infra/edge apply teardown-edge.tfplan
```

Use the actual edge inputs used when provisioning; if the file has a different name, substitute that name. This removes Front Door Premium, WAF, Private Link Service, edge DNS records, diagnostics and its alert before AKS removes the internal load balancer. Check the plan has no creations or unrelated changes. A DNS zone deletion later will make the existing Namecheap delegation nonfunctional; retain the domain and change its nameservers back to your chosen DNS provider when retiring the website.

## 4. Remove the application platform and observability

```bash
terraform -chdir=infra/nonprod plan -destroy \
  -var-file=../.generated/nonprod.auto.tfvars.json \
  -var-file=../.generated/access.auto.tfvars.json \
  -var-file=../.generated/lab.auto.tfvars.json \
  -out=teardown-nonprod.tfplan
terraform -chdir=infra/nonprod show -no-color teardown-nonprod.tfplan
# Only after reviewing every deletion:
terraform -chdir=infra/nonprod apply teardown-nonprod.tfplan
```

This removes AKS, VM/disks/IP, database, vault, identities, networking, DNS zone, monitoring workspaces, Grafana, DCR/DCE, alerts and any enabled project archive storage. Full AKS deletion removes the workloads/controllers too; a separate Helm uninstall is unnecessary when deleting the entire cluster. Azure also removes AKS's node resource group. Monitor workspace deletion removes its associated managed resource group. Verify both rather than deleting all similarly named groups.

If deletion fails, preserve state, investigate the named dependency and generate a fresh reviewed destroy plan. Do not use `terraform state rm`, blanket resource-group deletion, or disable unrelated locks to hide failures. Key Vault purge protection can retain a deleted vault for its retention period; do not attempt to bypass it or purge other vaults.

## 5. Remove the registry and image storage

```bash
terraform -chdir=infra/registry plan -destroy -var-file=../.generated/registry.auto.tfvars.json -out=teardown-registry.tfplan
terraform -chdir=infra/registry show -no-color teardown-registry.tfplan
# Only after reviewing the registry deletion:
terraform -chdir=infra/registry apply teardown-registry.tfplan
```

This deletes `acrnk81c108fc` and the stored backend/frontend images. The registry resource group remains until bootstrap cleanup because bootstrap owns that group. Confirm the edge, nonprod and registry states no longer contain managed resources.

## 6. Remove bootstrap last, after migrating its state locally

The state account cannot hold the state of its own deletion. First migrate bootstrap state to a private local file. Do not run the backend-generation script again after this migration.

```bash
python3 - "$TEARDOWN_BACKUP/bootstrap-final.tfstate" <<'PY'
import json
from pathlib import Path
import sys
target = Path(sys.argv[1]).resolve()
Path('infra/bootstrap/backend.local.tf').write_text(
    'terraform {\n  backend "local" {\n    path = ' + json.dumps(str(target)) + '\n  }\n}\n')
PY
terraform -chdir=infra/bootstrap init -migrate-state
terraform -chdir=infra/bootstrap state list
```

Review the migration prompt and confirm the local state retains the same bootstrap resource addresses. Preserve the original backup. Do not use `-reconfigure` here: the state must actually migrate.

Only now, in your local working copy, intentionally release the four source-level deletion guards. They stay enabled in the project's normal configuration:

```bash
python3 - <<'PY'
from pathlib import Path
p = Path('infra/bootstrap/main.tf')
s = p.read_text()
guard = 'lifecycle { prevent_destroy = true }'
if s.count(guard) != 4:
    raise SystemExit('Expected four guards; inspect the configuration before changing it.')
p.write_text(s.replace(guard, 'lifecycle { prevent_destroy = false }'))
PY
terraform -chdir=infra/bootstrap plan -destroy -out=teardown-bootstrap.tfplan
terraform -chdir=infra/bootstrap show -no-color teardown-bootstrap.tfplan
# Only after reviewing every deletion and confirming the backend is local:
terraform -chdir=infra/bootstrap apply teardown-bootstrap.tfplan
```

The original ignored `terraform.tfvars` supplies bootstrap inputs automatically. Terraform owns the `protect-terraform-state` Azure lock and removes it during this final destroy. The plan must include the project foundations, state storage and project identities/permissions only. If deletion order or lock enforcement causes a failure, inspect it and replan; never delete state storage while still using its remote backend.

Keep the final local state until verification is complete. Restore the source guards afterward with `git restore infra/bootstrap/main.tf` only if that file contains no other work you need. Do not commit a disabled guard or machine-specific backend.

## 7. Verify completion and billing

```bash
python3 scripts/teardown_inventory.py > reports/teardown-after.json
az group list --subscription b4207b90-6a00-470a-aa95-b154c688bb74 \
  --query '[].{name:name,managedBy:managedBy}' --output table
```

Confirm the four exact project groups and the previously recorded AKS/Monitor managed groups are gone. Confirm project custom roles recorded in step 1 and role assignments were removed through Terraform. Inspect the subscription resource list for any orphaned project resource using the recorded IDs, including optional disks/IP/storage. Investigate leftovers individually; never select deletion targets by prefix alone.

Check Cost Management after its reporting delay. Earlier usage can still appear after deletion; an invoice need not become zero. Soft-deleted vault/workspace recovery metadata is distinct from running infrastructure. Keep GitHub source and Namecheap registration unless you separately choose to cancel them. No scheduled destruction is configured by this PR.

References: [AKS deletion](https://learn.microsoft.com/en-us/azure/aks/delete-cluster), [AKS node resource group](https://learn.microsoft.com/en-us/azure/aks/faq), [Monitor workspace deletion](https://learn.microsoft.com/en-us/azure/azure-monitor/metrics/azure-monitor-workspace-manage?tabs=azure-portal), [Log Analytics deletion](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/delete-workspace).
