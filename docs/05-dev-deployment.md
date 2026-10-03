# Step 5 — private access, database bootstrap and Dev CD in one runbook

This bundle gets the first Dev workload running on the already-created private AKS cluster. Follow checkpoints A–D in order. You do not need a new GitHub PAT, ACR password, database password or Azure client secret. Terraform provisions the Azure additions; SQL and Kubernetes bootstrap are explicit one-time operator actions, and Helm owns application releases.

**This step establishes private deployment. Continue directly with [Step 6](06-complete-dev-lab.md) for the consolidated edge/observability setup and [Step 7](07-scenarios.md) for drills.** The next milestone keeps the agreed Front Door Premium → private ingress → `/` and `/api/` design, then adds Managed Prometheus/Grafana, DCR container logs, trace storage and alert simulations. Staging/prod remain deferred. No GitHub Actions build metrics are collected.

## What the bundle does and why

| Component | Purpose and authorization |
|---|---|
| Two-vCPU Ubuntu deployment VM | Lives in the reserved VNet subnet, resolves private AKS/DB/vault DNS. D2s_v4 + two D4s_v4 nodes uses the recorded 10-vCPU quota. No availability zone is selected. |
| Public VM IP and SSH NSG | Explicit outbound connectivity for Azure APIs/tools/public source checkout, plus operator SSH from one IPv4 `/32` only. AKS, DB and vault retain private access. This is a lab access compromise; VPN/Bastion/private runners are alternatives with additional cost/setup. |
| GitHub-hosted Actions → VM Run Command | Actions uses the existing Dev OIDC identity. It can start/deallocate and execute commands on this VM only. The VM uses that identity's existing AKS namespace access. No GitHub runner is registered on the VM, so public-repository PR jobs cannot target it as a runner. |
| Namespace and migration ServiceAccount | Operator creates them before Helm's pre-install migration hook. Dev deployer cannot create namespaces or cluster-wide grants. |
| Separate SQL roles | PostgreSQL must register the runtime/migration **principal object IDs**, separately from Azure RBAC. Runtime gets notes CRUD; migration gets schema-object creation, owns its tables/history, and runs Flyway. |
| Helm application chart | Deploys the same CI backend/frontend **digest pair**, nonroot/read-only containers, requests/limits, startup/readiness/liveness probes and graceful shutdown. |
| Key Vault CSI | Runtime workload identity mounts a nonsecret demonstration value over private access. No duplicate Kubernetes Secret synchronization. The app does not yet use this value as business configuration. |
| CI release validation | Accepts only successful `ci.yml` main-push artifacts, validates the archive digest, source/run/commit/platform and both ACR image references. CD never builds images. |
| Finite migration mode | CI tests the backend image against a new PostgreSQL database and confirms it migrates and exits. CI builds this version after merge; use that release for bootstrap. Older images without this mode must not be selected for this milestone. |

Run Command executes as root on the executor VM. That is real host authority, not a namespace-only shell. Its Azure role is scoped to this VM, while the attached identity's Kubernetes authorization is Dev namespace Writer. Trusted main code and the Dev environment control who can exercise that authority. Do not store operator credentials on this VM or run CD during operator bootstrap. Namespace Writer can execute pods and use workload identities inside its namespace; it is not an isolation boundary between trusted Dev deployers and Dev workloads.

The VM is automatically deallocated after a CD attempt. Disks/public IP and other services keep charging. Ubuntu uses the latest image within the specified 24.04 LTS offer at **VM creation**; application images remain SHA-tagged and digest-pinned. Tool clients are pinned; Helm 3 reaches end of support in November 2026, so revisit the client before continuing this lab beyond that date.

## A. Merge, provision the access VM and export actual configuration

First merge this PR after checks pass, then on your laptop:

```bash
git switch main
git pull --ff-only
```

Wait for **Test and build** on this merge to succeed and publish its release. Record that full merge commit SHA as `RELEASE_SHA`. Do not use a PR's synthetic merge SHA or reuse an older backend image lacking the migration mode.

Create a dedicated SSH key if it does not already exist. Keep the private file on your laptop:

```bash
ssh-keygen -t ed25519 -f "$HOME/.ssh/notekeeper-lab" -C notekeeper-lab
```

Check current quota and regional SKU restrictions before adding a VM:

```bash
az vm list-usage --location centralindia --output table
az vm list-skus --location centralindia --resource-type virtualMachines \
  --size Standard_D2s_v4 --all --output json
```

You need two available regional vCPUs and two DSv4-family vCPUs. A restriction limited to a particular availability zone is compatible with leaving zones unset; a region-wide restriction is not. Actual capacity is only established when Azure provisions the VM. If the VM cannot be allocated, stop here and share the allocation error; do not replace the AKS SKU or request more nodes automatically.

Use your actual public IPv4 (from your network/router or an IP-check service):

```bash
python3 scripts/configure_access.py \
  --operator-ip YOUR_PUBLIC_IPV4 \
  --ssh-public-key "$HOME/.ssh/notekeeper-lab.pub"

terraform -chdir=infra/nonprod fmt -check
terraform -chdir=infra/nonprod validate
terraform -chdir=infra/nonprod plan \
  -var-file=../.generated/nonprod.auto.tfvars.json \
  -var-file=../.generated/access.auto.tfvars.json \
  -out=dev-access.tfplan
terraform -chdir=infra/nonprod show -no-color dev-access.tfplan
```

Expected: **7 additions, no replacement/destroy and no AKS/database/vault changes**: public IP, NSG, NIC, NIC/NSG association, VM, custom role, scoped assignment. Output additions are normal. If you see other changes, review them before proceeding.

```bash
terraform -chdir=infra/nonprod apply dev-access.tfplan
terraform -chdir=infra/nonprod output -json platform > infra/.generated/dev-platform.json
terraform -chdir=infra/nonprod output -json deployment_vm > infra/.generated/dev-vm.json
terraform -chdir=infra/nonprod plan \
  -var-file=../.generated/nonprod.auto.tfvars.json \
  -var-file=../.generated/access.auto.tfvars.json
```

Expected follow-up: **No changes**. Always include both variable files on subsequent plans/applies. Omitting access inputs sets the VM-enabled flag back to false and would propose deleting these additions. Existing bootstrap/registry state stays untouched.

Get the VM address, and validate its SSH host key through the authenticated Azure control plane:

```bash
VM_IP=$(python3 -c 'import json; print(json.load(open("infra/.generated/dev-vm.json"))["public_ip"])')
az vm run-command invoke -g rg-nk-nonprod -n vm-nk-dev-deploy \
  --command-id RunShellScript \
  --scripts 'cat /etc/ssh/ssh_host_ed25519_key.pub' \
  --query 'value[].message' -o tsv
```

Copy only the returned `ssh-ed25519 AAAA...` public key line into `infra/.generated/vm-host.pub`, then record and fingerprint it:

```bash
ssh-keygen -lf infra/.generated/vm-host.pub
printf '%s %s\n' "$VM_IP" "$(cat infra/.generated/vm-host.pub)" >> "$HOME/.ssh/known_hosts"
ssh -o StrictHostKeyChecking=yes -i "$HOME/.ssh/notekeeper-lab" "labadmin@$VM_IP"
```

On the VM, wait for tool installation. First boot can take several minutes:

```bash
sudo cloud-init status --wait
az version
kubectl version --client
helm version
kubelogin --version
exit
```

If cloud-init fails, inspect `sudo tail -n 80 /var/log/cloud-init-output.log`; do not continue without all tools installed. No credentials are present in cloud-init. A changed SSH IP requires updating access inputs and a reviewed Terraform plan, not opening SSH to the Internet.

## B. Retrieve the CI release and configure GitHub Dev

On your laptop, sign in to GitHub CLI if needed (`gh auth login`), then use the successful full main CI commit:

```bash
RELEASE_SHA=PASTE_FULL_SUCCESSFUL_MAIN_COMMIT_SHA
GH_TOKEN="$(gh auth token)" python3 scripts/fetch_release.py "$RELEASE_SHA" \
  --registry acrnk81c108fc.azurecr.io \
  --output infra/.generated/dev-release.json

python3 scripts/deployment_config.py \
  --platform infra/.generated/dev-platform.json \
  --release infra/.generated/dev-release.json \
  --registry acrnk81c108fc.azurecr.io \
  --output infra/.generated/dev-values.json

python3 scripts/configure_github_dev.py \
  --platform infra/.generated/dev-platform.json \
  --vm infra/.generated/dev-vm.json \
  --registry acrnk81c108fc.azurecr.io
```

The GitHub setup script sets Dev's main-only branch policy and seven environment variables from the outputs; none is a secret. In **Settings → Environments → dev**, inspect that only branch `main` is allowed. Add your account as a required reviewer if available for your repository/plan. For this single-operator lab, allow self-approval if you enable reviews. Existing qualified OIDC subjects containing immutable repository/owner IDs remain unchanged.

Copy only public/nonsecret configuration to the VM:

```bash
scp -o StrictHostKeyChecking=yes -i "$HOME/.ssh/notekeeper-lab" \
  infra/.generated/dev-platform.json infra/.generated/dev-values.json \
  "labadmin@$VM_IP:"
```

## C. Initialize the private database once using the operator

SSH to the VM. Avoid concurrent Deploy Dev runs during this session:

```bash
ssh -o StrictHostKeyChecking=yes -i "$HOME/.ssh/notekeeper-lab" "labadmin@$VM_IP"
git clone https://github.com/anuragdchowdhury/ci-cd-project.git
cd ci-cd-project
git checkout --detach PASTE_FULL_MERGED_DEPLOYMENT_PR_COMMIT_SHA
```

Use the deployment PR's merged commit (or a later reviewed main commit containing this bundle). Do not execute arbitrary branch changes here. Start a subshell so cleanup also runs if a command fails:

```bash
(
  set -e
  export AZURE_CONFIG_DIR="$(mktemp -d)"
  export KUBECONFIG="$(mktemp)"
  trap 'rm -rf "$AZURE_CONFIG_DIR"; rm -f "$KUBECONFIG"' EXIT
  az login --tenant 133815cf-acdc-4089-a1e7-fce0de2fe1b4 --use-device-code
  az account set --subscription b4207b90-6a00-470a-aa95-b154c688bb74
  python3 scripts/bootstrap_dev.py \
    --platform "$HOME/dev-platform.json" \
    --values "$HOME/dev-values.json"
)
exit
```

Sign in with the same operator who is the PostgreSQL Entra administrator. The registered admin login is the API-returned 63-character name exported by Terraform. The script obtains a fresh PostgreSQL audience token in the subprocess environment and uses `sslmode=verify-full`; it does not write a database password or print the token.

The script registers both identity object IDs; existing roles must match their expected object IDs and not be admins. It grants schema creation only to migration, creates the restricted Dev namespace and migration ServiceAccount, writes the nonsecret lab value to the private vault, installs Helm in migration-only mode, then grants runtime CRUD on `notes` **after the table exists**. It validates that runtime cannot create schema objects or read Flyway history. Expected markers: `NOTEKEEPER_BOOTSTRAP_OK`, then `NOTEKEEPER_DB_READY`.

A SQL-bootstrap failure can leave partial setup, but it is safe to rerun after resolving the error; role mapping is checked before reuse. Do not continue to CD until the final marker appears. Azure role/federation changes can take time to propagate; failed migration Job events distinguish pull/auth errors. No API/frontend Deployment is started during this bootstrap install.

## D. Deploy the same image pair through GitHub Actions

Back on the laptop:

```bash
gh workflow run deploy-dev.yml --repo anuragdchowdhury/ci-cd-project \
  --ref main -f release_sha="$RELEASE_SHA"
gh run list --repo anuragdchowdhury/ci-cd-project \
  --workflow deploy-dev.yml --limit 3
```

Open **Actions → Deploy Dev**, approve the environment if configured, and inspect the run. It validates the chosen CI artifact, authenticates via OIDC, starts the VM, invokes reviewed main-commit deployment code inside the VNet, runs Flyway before rollout, and deploys both digests with Helm `--atomic --wait`. It checks rollout readiness, the mounted vault file, actual pod image references/no pull secret, and frontend → backend → PostgreSQL CRUD. Only then does it print `NOTEKEEPER_DEPLOY_OK FULL_SHA`. ARM Run Command success without this marker is a deployment failure. The VM is then deallocated to save compute.

**Rollback limits:** Helm rolls Kubernetes release resources back if install/upgrade readiness fails. It does not reverse completed SQL migrations. A later smoke-check failure marks CD failed but does not automatically undo the successful Helm release. Use backward-compatible additive migrations, inspect the failure, and manually redeploy the previous successful digest pair if compatible. A new migration creating tables must explicitly grant the runtime's required rights; bootstrap grants only the current `notes` table, not every future table or Flyway history.

## See the private app locally and inspect it

Start the VM when you need a training session; it is deallocated after CD:

```bash
az vm start -g rg-nk-nonprod -n vm-nk-dev-deploy
ssh -o StrictHostKeyChecking=yes -i "$HOME/.ssh/notekeeper-lab" \
  -L 8080:127.0.0.1:8080 "labadmin@$VM_IP"
```

On the VM, use its managed identity with disposable credentials:

```bash
(
  export AZURE_CONFIG_DIR="$(mktemp -d)"
  export KUBECONFIG="$(mktemp)"
  trap 'rm -rf "$AZURE_CONFIG_DIR"; rm -f "$KUBECONFIG"' EXIT
  az login --identity --client-id a21d399c-b496-4ddc-ab16-8387c42ea409 --output none
  az account set --subscription b4207b90-6a00-470a-aa95-b154c688bb74
  az aks get-credentials -g rg-nk-nonprod -n aks-notekeeper-nonprod --file "$KUBECONFIG"
  kubelogin convert-kubeconfig -l azurecli
  kubectl -n notekeeper-dev get pods,services,jobs
  kubectl -n notekeeper-dev logs deployment/notekeeper-api --tail=30
  kubectl -n notekeeper-dev port-forward service/frontend 8080:8080 --address 127.0.0.1
)
```

Open **http://localhost:8080** on your laptop. Create/edit/delete notes. API requests produce structured container logs and request IDs; actual distributed traces, Grafana RED dashboards and managed log ingestion are enabled in the monitoring milestone. You can check an API request's response `X-Request-Id` now, but do not call it a trace ID.

Stop port-forward with Ctrl+C, exit SSH, then deallocate the VM:

```bash
az vm deallocate -g rg-nk-nonprod -n vm-nk-dev-deploy
```

The API management port stays ClusterIP/private, so readiness/metrics are not exposed publicly. This phase uses Nginx's existing `/api/` proxy through the frontend service for private testing. The later ingress routes `/api/` directly to backend and `/` to frontend behind Front Door Premium.

## Checkpoint to share

Share the access-plan summary, follow-up `No changes`, final `NOTEKEEPER_DB_READY`, Deploy Dev result/success marker, and whether the local tunneled UI works. Do not share Terraform state/plans, kubeconfig, SSH private keys or access tokens. After these pass we can bundle Front Door/ingress and observability, then run overload, latency, alert, trace and Terraform drift exercises.

## References

- [AKS private cluster access](https://learn.microsoft.com/en-us/azure/aks/private-clusters)
- [Action Run Command and its host authority](https://learn.microsoft.com/en-us/azure/virtual-machines/run-command-overview)
- [Run Command IAM action](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/compute)
- [PostgreSQL Entra role registration](https://learn.microsoft.com/en-us/azure/postgresql/security/security-manage-entra-users)
- [Key Vault CSI workload identity](https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-identity-access)
- [Helm 3 support lifecycle](https://helm.sh/blog/helm-v3-end-of-life)
